import json, glob
from pathlib import Path

# --- B3: merge chunk files, record real token usage from Agent result ---
chunks = sorted(glob.glob('graphify-out/.graphify_chunk_*.json'))
all_nodes, all_edges, all_hyper = [], [], []
for c in chunks:
    d = json.loads(Path(c).read_text(encoding='utf-8'))
    all_nodes += d.get('nodes', [])
    all_edges += d.get('edges', [])
    all_hyper += d.get('hyperedges', [])
new = {'nodes': all_nodes, 'edges': all_edges, 'hyperedges': all_hyper,
       'input_tokens': 102364, 'output_tokens': 0}  # real usage from Agent result (total subagent tokens)
Path('graphify-out/.graphify_semantic_new.json').write_text(json.dumps(new, ensure_ascii=False), encoding='utf-8')
print(f'Merged {len(chunks)} chunk(s): {len(all_nodes)} nodes, {len(all_edges)} edges')

# --- save to cache ---
from graphify.cache import save_semantic_cache
saved = save_semantic_cache(all_nodes, all_edges, all_hyper)
print(f'Cached {saved} files')

# --- merge cached + new (no prior cache) ---
sem = new
Path('graphify-out/.graphify_semantic.json').write_text(json.dumps(sem, ensure_ascii=False), encoding='utf-8')

# --- Part C: merge AST + semantic ---
ast = json.loads(Path('graphify-out/.graphify_ast.json').read_text(encoding='utf-8'))
seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])
merged = {'nodes': merged_nodes, 'edges': ast['edges'] + sem['edges'],
          'hyperedges': sem.get('hyperedges', []),
          'input_tokens': sem['input_tokens'], 'output_tokens': sem['output_tokens']}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Final extraction: {len(merged_nodes)} nodes, {len(merged["edges"])} edges ({len(ast["nodes"])} AST + {len(sem["nodes"])} semantic)')

# --- Step 4: build, cluster, analyze, report ---
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json

detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding='utf-8'))
G = build_from_json(merged)
communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': merged['input_tokens'], 'output': merged['output_tokens']}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens,
                  r'c:\Users\Karthik\OneDrive\Desktop\ASTA', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report, encoding='utf-8')
to_json(G, communities, 'graphify-out/graph.json')

analysis = {'communities': {str(k): v for k, v in communities.items()},
            'cohesion': {str(k): v for k, v in cohesion.items()},
            'gods': gods, 'surprises': surprises, 'questions': questions}
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding='utf-8')
if G.number_of_nodes() == 0:
    raise SystemExit('ERROR: Graph is empty')
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')

# print community membership summaries for labeling
from collections import Counter, defaultdict
comm_nodes = defaultdict(list)
for nid, cid in communities.items():
    comm_nodes[cid].append(nid)
for cid, nids in sorted(comm_nodes.items(), key=lambda x: -len(x[1]))[:30]:
    labels_sample = [G.nodes[n].get('label', n) for n in nids]
    files = Counter()
    for n in nids:
        sf = G.nodes[n].get('source_file', '') or ''
        parts = sf.replace('\\', '/').split('/')
        files['/'.join(parts[:2]) if len(parts) > 1 else sf] += 1
    top_files = ', '.join(f'{f}({c})' for f, c in files.most_common(3))
    print(f'COMM {cid}: {len(nids)} nodes | dirs: {top_files} | sample: {labels_sample[:8]}')
