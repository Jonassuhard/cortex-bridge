export type BridgeDiagramLocale = "fr" | "en";

export interface BridgeDiagramNode {
  id: "user" | "profile" | "chatgpt" | "preflight" | "executor" | "ollama" | "workspace" | "evidence";
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
    user: ["Toi", "demande explicite"], profile: ["Profil Playwright", "session dédiée"], chatgpt: ["ChatGPT", "conversation"], preflight: ["Préflight", "capacités et limites"], executor: ["Exécuteur déterministe", "outils validés"], ollama: ["Ollama", "optionnel"], workspace: ["Workspace", "fichiers et commandes"], evidence: ["Preuves et statuts", "retour vérifié"],
  },
  en: {
    user: ["You", "explicit request"], profile: ["Playwright profile", "dedicated session"], chatgpt: ["ChatGPT", "conversation"], preflight: ["Preflight", "capabilities and limits"], executor: ["Deterministic executor", "validated tools"], ollama: ["Ollama", "optional"], workspace: ["Workspace", "files and commands"], evidence: ["Evidence and status", "verified return"],
  },
} as const;

export function createBridgeDiagramModel({ locale, includeOllama, reducedMotion }: { locale: BridgeDiagramLocale; includeOllama: boolean; reducedMotion: boolean }): BridgeDiagramModel {
  const order: BridgeDiagramNode["id"][] = ["user", "profile", "chatgpt", "preflight", "executor", ...(includeOllama ? ["ollama" as const] : []), "workspace", "evidence"];
  const nodes = order.map((id) => ({ id, label: labels[locale][id][0], detail: labels[locale][id][1] }));
  const edges = order.slice(0, -1).map((from, index) => ({ from, to: order[index + 1] }));
  return {
    nodes,
    edges,
    animated: !reducedMotion,
    description: locale === "fr"
      ? "Flux utilisateur vers un profil Playwright dédié, ChatGPT, le préflight, l’exécuteur déterministe, le workspace, puis les preuves et statuts."
      : `User flow through a dedicated Playwright profile, ChatGPT, preflight, deterministic execution${includeOllama ? ", optional Ollama" : ""}, workspace, evidence, and status.`,
  };
}
