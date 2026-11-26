from api.backend import GraphBackend
from api.schemas import GraphLink, GraphNode, GraphViewOut

KNOWN_CHECK = 500
KNOWN_EXTRA = 5


def node_id(kind: str, ext_id: str) -> str:
    return f"{kind}:{ext_id}"


def build_graph_view(
    backend: GraphBackend, disease_id: str, k: int, max_paths: int
) -> GraphViewOut | None:
    disease = backend.get_disease(disease_id)
    if disease is None:
        return None
    root = node_id("Disease", disease_id)
    nodes: dict[str, GraphNode] = {
        root: GraphNode(id=root, kind="Disease", name=disease.name, role="disease")
    }
    links: dict[tuple[str, str, str, str], GraphLink] = {}
    known = dict(backend.known_drugs(disease_id, KNOWN_CHECK))
    candidates = backend.candidates(disease_id, k)
    genes: dict[str, GraphNode] = {}

    def add_link(link: GraphLink) -> None:
        links.setdefault((link.source, link.target, link.kind, link.label), link)

    for cand in candidates:
        did = node_id("Compound", cand.drug_id)
        role = "known" if cand.drug_id in known else "predicted"
        nodes[did] = GraphNode(id=did, kind="Compound", name=cand.drug_name, role=role)
        add_link(
            GraphLink(
                source=did, target=root, kind="predicted", label="predicted", score=cand.score
            )
        )
        if cand.drug_id in known:
            add_link(GraphLink(source=did, target=root, kind="known", label="treats"))
    for cand in candidates:
        for path in backend.paths(cand.drug_id, disease_id, max_paths):
            ids = [node_id(n.kind, n.id or n.name) for n in path.nodes]
            for n, nid in zip(path.nodes, ids):
                if n.kind == "Gene" and nid not in genes:
                    genes[nid] = GraphNode(id=nid, kind="Gene", name=n.name, role="gene")
            for src, dst, etype in zip(ids, ids[1:], path.edges):
                add_link(GraphLink(source=src, target=dst, kind="evidence", label=etype))
    nodes.update(genes)
    extras = 0
    for drug_id, name in sorted(known.items(), key=lambda t: (t[1], t[0])):
        did = node_id("Compound", drug_id)
        if did in nodes or extras >= KNOWN_EXTRA:
            continue
        nodes[did] = GraphNode(id=did, kind="Compound", name=name, role="known")
        add_link(GraphLink(source=did, target=root, kind="known", label="treats"))
        extras += 1
    return GraphViewOut(disease=disease, nodes=list(nodes.values()), links=list(links.values()))
