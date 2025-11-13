# retrieval/fusion.py
def rrf(rankings, k=60):
    scores={}
    for lst in rankings:
        for rank,(doc_id,_) in enumerate(lst,1):
            scores[doc_id]=scores.get(doc_id,0)+1/(k+rank)
    return sorted(scores.items(), key=lambda x:x[1], reverse=True)
