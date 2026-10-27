import json,os,re,sys,random,urllib.request
ROOT=sys.argv[1]; S=sys.argv[2]
key=[l.split("=",1)[1].strip().strip('"\'') for l in open(os.path.join(ROOT,".env")) if l.startswith("NVIDIA_API_KEY=")][0]
d=json.load(open(f"{S}/persona_out.json")); r=d["replies"]
ids={"hume":"David Hume","nightingale":"Florence Nightingale","weber":"Max Weber","ostrom":"Elinor Ostrom","darwin":"Charles Darwin","ibn_al_haytham":"Ibn al-Haytham"}
names=list(ids.values())+["Hume","Nightingale","Weber","Ostrom","Darwin","Haytham","Alhazen","Verstehen"]
res=[]
for seed in (1,2,3):
    keys=list(ids); random.seed(seed); random.shuffle(keys)
    anon="\n\n".join(f"[Reply {i+1}]\n"+re.sub("|".join(map(re.escape,names)),"[REDACTED]",r[k]) for i,k in enumerate(keys))
    body={"model":"nvidia/nemotron-3-ultra-550b-a55b","temperature":0,"max_tokens":3000,"messages":[{"role":"user","content":f"Six replies were written by these thinkers, one each: {', '.join(ids.values())}. Names and signature terms are redacted. Attribute each reply to one thinker (each used once) from reasoning style and concerns. Answer with ONLY a JSON object on the last line, like {{\"1\": \"David Hume\", ...}}.\n\n{anon}"}]}
    req=urllib.request.Request("https://integrate.api.nvidia.com/v1/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    txt=json.load(urllib.request.urlopen(req,timeout=300))["choices"][0]["message"]["content"] or ""
    m=re.findall(r"\{[^{}]*\}",txt); g=json.loads(m[-1]) if m else {}
    rows=[(ids[k],g.get(str(i+1))) for i,k in enumerate(keys)]
    res.append(sum(a==b for a,b in rows)); print("run",seed,"correct",res[-1],"/6",[b for a,b in rows if a!=b and b] and [f"{a}->{b}" for a,b in rows if a!=b])
print("total",sum(res),"/18")
