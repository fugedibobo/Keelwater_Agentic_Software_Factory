"""Stage 5: embed verified insights and group them into opportunities with stable ids (architecture section 4)."""

from collections import Counter

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage

from . import config, prompts
from .contracts import ClusterLabelOutput, Opportunity, OpportunityInsight
from .store import opportunity_id

BATCH = 64
LABEL_MEMBERS = 8


def unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n else v


def embed_text(ins):
    return f"{ins['quote']}\n{ins['problem']}"


def embed_missing(ctx, insights):
    todo = [i for i in insights if not i["embedding"]]
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        vecs = ctx.gateway.embed("embed", [embed_text(i) for i in chunk], target_type="insight", target_id=chunk[0]["insight_id"])
        for i, v in zip(chunk, vecs):
            i["embedding"] = list(v)
            ctx.store.update("insight", {"insight_id": i["insight_id"]}, {"embedding": i["embedding"]})


def groups(vectors, distance):
    """Average-linkage agglomerative clusters at a cosine distance threshold: lists of row positions, smallest first."""
    if len(vectors) < 2:
        return [[k] for k in range(len(vectors))]
    labels = fcluster(linkage(np.array(vectors), method="average", metric="cosine"), t=distance, criterion="distance")
    out = {}
    for pos, lab in enumerate(labels):
        out.setdefault(lab, []).append(pos)
    return sorted(out.values())


def majority_bucket(store, members):
    snip_bucket = {t["snippet_id"]: t["bucket"] for t in store.select("triage") if t["bucket"]}
    counts = Counter(snip_bucket[m["snippet_id"]] for m in members if m["snippet_id"] in snip_bucket)
    # shortcut: no triage bucket for any member falls back to the first taxonomy bucket, upgrade if #4 leaves buckets null
    return min(counts, key=lambda b: (-counts[b], b)) if counts else config.bucket_ids()[0]


def label(ctx, opp_id, members, system, version):
    lines = "\n".join(f"- problem: {m['problem']}\n  quote: {m['quote']}" for m in members[:LABEL_MEMBERS])
    out = ctx.gateway.chat("cluster_label", [{"role": "system", "content": system}, {"role": "user", "content": lines}],
                           target_type="opportunity", target_id=opp_id, prompt_version=version)
    return ClusterLabelOutput.model_validate(out)


def run(ctx):
    store = ctx.store
    distance = ctx.config["pipeline"]["cluster"]["distance"]
    tau = 1 - distance
    placed = {r["insight_id"] for r in store.select("opportunity_insight")}
    insights = [i for i in store.select("insight", order_by="insight_id") if i["quote_match"] != "failed" and i["insight_id"] not in placed]
    if not insights:
        return
    embed_missing(ctx, insights)
    squad_of = {b["id"]: b["squad"] for b in config.load("taxonomy")["buckets"]}
    # state of every open opportunity: [sum of member unit vectors, member count]
    state = {}
    for o in store.select("opportunity"):
        if o["merged_into"] is None and o["centroid"]:
            n = len(store.select("opportunity_insight", {"opportunity_id": o["opportunity_id"]}))
            state[o["opportunity_id"]] = [np.asarray(o["centroid"], float) * n, n]
    rest = []
    for ins in insights:  # id order: join the nearest centroid, else wait for clustering among themselves
        v = unit(ins["embedding"])
        best = max(((float(v @ unit(s / n)), oid) for oid, (s, n) in sorted(state.items())), default=None)
        if best and best[0] >= tau:
            oid = best[1]
            state[oid][0], state[oid][1] = state[oid][0] + v, state[oid][1] + 1
            store.insert("opportunity_insight", OpportunityInsight(opportunity_id=oid, insight_id=ins["insight_id"], similarity=min(1.0, max(0.0, best[0]))))
            store.update("opportunity", {"opportunity_id": oid}, {"centroid": (state[oid][0] / state[oid][1]).tolist()})
        else:
            rest.append(ins)
    system, version = prompts.load_prompt("cluster", "label")
    for grp in groups([unit(i["embedding"]) for i in rest], distance):
        members = [rest[p] for p in grp]  # rest is in id order, so members[0] holds the smallest id
        oid = opportunity_id(members[0]["insight_id"])
        centroid = np.mean([unit(m["embedding"]) for m in members], axis=0)
        lab = label(ctx, oid, members, system, version)
        bucket = majority_bucket(store, members)
        store.insert("opportunity", Opportunity(opportunity_id=oid, title=lab.title, problem_statement=lab.problem_statement,
                                                bucket=bucket, squad=squad_of[bucket], first_seen_as_of=ctx.as_of,
                                                centroid=centroid.tolist()), replace=True)
        for m in members:
            store.insert("opportunity_insight", OpportunityInsight(opportunity_id=oid, insight_id=m["insight_id"],
                                                                   similarity=min(1.0, max(0.0, float(unit(m["embedding"]) @ unit(centroid))))), replace=True)
