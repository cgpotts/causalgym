from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
import random
from plotnine import ggplot, aes, facet_wrap, facet_grid, geom_bar, theme, element_text, geom_errorbar, ggtitle, geom_hline, geom_point, geom_violin
from plotnine.scales import scale_color_manual, scale_x_log10, ylim
import pandas as pd
import argparse

def load_data():
    # read stimuli
    with open("stimuli2.json", "r") as f:
        stimuli = json.load(f)
    names = []
    for gender in stimuli['names']:
        names.extend([(name, gender) for name in stimuli['names'][gender]])
    
    # construct all possible sentences
    sentences = []
    for i, stimulus in enumerate(stimuli['sentences']):
        for name1 in names:
            subbed = stimulus.replace("<name1>", name1[0])
            for name2 in names:
                if name2[0] == name1[0]: continue
                genders = [name1[1], name2[1]]
                subbed2 = subbed.replace("<name2>", name2[0])
                for gender in set(genders):
                    subbed3 = subbed2.replace("<pronoun>", gender)
                    referents = []
                    if name1[1] == gender: referents.append(name1[0])
                    if name2[1] == gender: referents.append(name2[0])
                    sentences.append({
                        "sent": subbed3,
                        "match_name1": name1[0] in referents,
                        "match_name2": name2[0] in referents,
                        "name1_gender": name1[1],
                        "name2_gender": name2[1],
                        "pronoun_gender": gender,
                        "stimulus": i
                    })
    
    return sentences

@torch.no_grad()
def main(name="gpt2-medium"):
 
    # load model
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(name)
    tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(name).to(device)

    # get data
    sentences = load_data()
    random.shuffle(sentences)
    print(len(sentences))

    # generate next token distributions
    distribs = []
    sents = [x['sent'] for x in sentences]
    for batch in range(0, len(sents), 200):
        inputs = tokenizer(sents[batch:batch+200], return_tensors="pt", padding=True).to(device)
        logits = model(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        for i in range(200):
            distrib = probs[i, inputs['attention_mask'][i] == 1][-1]
            distribs.append(distrib)

    # get kl divergence between distributions
    kldivs = []
    for i in range(len(sents)):
        for j in range(len(sents)):
            if i == j: continue
            kldiv = torch.nn.functional.kl_div(distribs[i].log(), distribs[j], reduction="sum")
            label = [sentences[i]["match_name1"], sentences[i]["match_name2"], sentences[j]["match_name1"], sentences[j]["match_name2"]]
            label = "".join(["T" if x else "F" for x in label])
            kldivs.append({
                "sent1": sents[i],
                "sent2": sents[j],
                "same": label,
                "first": label[:2],
                "second": label[2:],
                "pronoun_gender1": sentences[i]["pronoun_gender"],
                "pronoun_gender2": sentences[j]["pronoun_gender"],
                "kldiv": kldiv.item()
            })
    
    # dump
    with open("logs/kldivs.json", "w") as f:
        json.dump(kldivs, f)
    
    # plot
    # df = pd.DataFrame(kldivs)
    # plot = (ggplot(df, aes(x="same", y="kldiv")) + geom_violin())
    # plot.save("kldiv.png", dpi=300)

    # print top 10 tokens
    # print(sent)
    # for i in torch.argsort(distrib, descending=True)[:10]:
    #     print(tokenizer.decode([i.item()]), distrib[i].item())
    # print()

    # distribs.append(distrib)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, default="gpt2-medium")
    args = parser.parse_args()
    main(args.name)