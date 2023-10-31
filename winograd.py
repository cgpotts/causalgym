from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import re
from tqdm import tqdm
import argparse
from models import MODELS, WEIGHTS

options_regex = re.compile(r"\[(.*?)/(.*?)\]")
softmax = torch.nn.Softmax(dim=-1)

def load_data():
    data = []
    with open("data/winograd.txt", "r") as f:
        lines = f.readlines()
        for i in range(0, len(lines), 4):
            sentence = lines[i].strip()
            question = lines[i+1].strip()
            answers = lines[i+2].strip().split("/")

            # get two options in sentence
            option1, option2 = options_regex.findall(sentence)[0]

            data.append({
                "sentence1": options_regex.sub(option1, sentence),
                "question1": options_regex.sub(option1, question) + (' The' if answers[0].islower() else ''),
                "answer1": answers[0],
                "sentence2": options_regex.sub(option2, sentence),
                "question2": options_regex.sub(option2, question) + (' The' if answers[0].islower() else ''),
                "answer2": answers[1],
            })
            
    return data

@torch.no_grad()
def experiment(model="gpt2", batch_size=1):
    data = load_data()
    fout = open("data/winograd_out.txt", "w")

    # load model
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model)
    tokenizer.pad_token = tokenizer.eos_token
    causal_model = AutoModelForCausalLM.from_pretrained(
        model,
        torch_dtype=WEIGHTS.get(model, torch.bfloat16) if device == "cuda:0" else torch.float32
    ).to(device)
    causal_model.eval()

    # metrics
    score, score_strict = 0, 0

    # generate
    for d in tqdm(data):
        sent1 = ' '.join([d["sentence1"], d["question1"]])
        sent2 = ' '.join([d["sentence2"], d["question2"]])
        fout.write(f"{d}\n")

        sent1 = tokenizer(sent1, return_tensors="pt").to(device)
        sent2 = tokenizer(sent2, return_tensors="pt").to(device)

        answer1 = tokenizer([' ' + d["answer1"]], return_tensors="pt").input_ids.to(device)[0]
        answer2 = tokenizer([' ' + d["answer2"]], return_tensors="pt").input_ids.to(device)[0]
        for i in range(min(answer1.shape[0], answer2.shape[0])):
            if answer1[i] != answer2[i]:
                answer1 = answer1[i]
                answer2 = answer2[i]
                break
        fout.write(f"{answer1}, {answer2}\n")

        # inference
        out1 = causal_model(**sent1)
        out2 = causal_model(**sent2)
        probs = [softmax(out1.logits), softmax(out2.logits)]
        logits = [out1.logits, out2.logits]
        probs1 = [probs[0][0][-1][answer1], probs[0][0][-1][answer2]]
        probs2 = [probs[1][0][-1][answer1], probs[1][0][-1][answer2]]

        # print topk
        for i in range(2):
            topk = torch.topk(logits[i][0][-1], 10)
            for j in range(10):
                fout.write(f"{topk.indices[j]:>7} {tokenizer.decode(topk.indices[j].unsqueeze(0)):<20} {topk.values[j]:>10.4} {probs[i][0][-1][topk.indices[j]]:>10.4%}\n")
            fout.write("\n")
        fout.write(f"{probs1}")
        fout.write(f"{probs2}")
        
        # scores
        if probs1[0] > probs1[1]:
            score += 0.5
        if probs2[1] > probs2[0]:
            score += 0.5
        if probs1[0] > probs1[1] and probs2[1] > probs2[0]:
            score_strict += 1
    
    # output scores
    fout.write(f"Score: {(score / len(data)):.4%}\n")
    fout.write(f"Strict Score: {(score_strict / len(data)):.4%}\n")
    fout.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt2", help="name of model")
    args = parser.parse_args()
    print(vars(args))

    if args.model == "all":
        for model in MODELS:
            args.model = model
            experiment(**vars(args))
            torch.cuda.empty_cache()
    else:
        experiment(**vars(args))

if __name__ == "__main__":
    main()