export type BridgeDiagramLocale = "fr" | "en";

export interface BridgeDiagramNode {
  id: "user" | "extension" | "chatgpt" | "preflight" | "executor" | "ollama" | "workspace" | "evidence";
  label: string;
  detail: string;
}

export interface BridgeDiagramModel {
  nodes: BridgeDiagramNode[];
  edges: { from: BridgeDiagramNode["id"]; to: BridgeDiagramNode["id"] }[];
  description: string;
  animated: boolean;
}

const labels = {
  fr: {
    user: ["Toi", "demande explicite"], extension: ["Extension Chrome", "jumelage local"], chatgpt: ["ChatGPT", "même fenêtre"], preflight: ["Préflight", "capacités et limites"], executor: ["Exécuteur déterministe", "outils validés"], ollama: ["Ollama", "optionnel"], workspace: ["Workspace", "fichiers et commandes"], evidence: ["Preuves et statuts", "retour vérifié"],
  },
  en: {
    user: ["You", "explicit request"], extension: ["Chrome extension", "local pairing"], chatgpt: ["ChatGPT", "same window"], preflight: ["Preflight", "capabilities and limits"], executor: ["Deterministic executor", "validated tools"], ollama: ["Ollama", "optional"], workspace: ["Workspace", "files and commands"], evidence: ["Evidence and status", "verified return"],
  },
} as const;

export function createBridgeDiagramModel({ locale, includeOllama, reducedMotion }: { locale: BridgeDiagramLocale; includeOllama: boolean; reducedMotion: boolean }): BridgeDiagramModel {
  const order: BridgeDiagramNode["id"][] = ["user", "extension", "chatgpt", "preflight", "executor", ...(includeOllama ? ["ollama" as const] : []), "workspace", "evidence"];
  const nodes = order.map((id) => ({ id, label: labels[locale][id][0], detail: labels[locale][id][1] }));
  const edges = order.slice(0, -1).map((from, index) => ({ from, to: order[index + 1] }));
  return {
    nodes,
    edges,
    animated: !reducedMotion,
    description: locale === "fr"
      ? "Flux utilisateur via l’extension locale vers ChatGPT dans la même fenêtre Chrome, puis le préflight, l’exécuteur déterministe, le workspace et les preuves."
      : `User flow through the local extension to ChatGPT in the same Chrome window, preflight, deterministic execution${includeOllama ? ", optional Ollama" : ""}, workspace, evidence, and status.`,
  };
}
