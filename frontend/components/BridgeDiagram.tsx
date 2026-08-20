"use client";

import { createBridgeDiagramModel } from "@/lib/bridge-diagram-model";

const positions = [
  [70, 70], [250, 70], [430, 70], [610, 70],
  [160, 220], [340, 220], [520, 220], [680, 220],
] as const;

export function BridgeDiagram({ includeOllama = false }: { includeOllama?: boolean }) {
  const model = createBridgeDiagramModel({ locale: "fr", includeOllama, reducedMotion: false });
  const position = new Map(model.nodes.map((node, index) => [node.id, positions[index]]));
  return (
    <figure className={`bridge-diagram ${model.animated ? "is-animated" : ""}`}>
      {/* oxlint-disable-next-line jsx-a11y/prefer-tag-over-role -- SVG title and desc expose the full diagram. */}
      <svg viewBox="0 0 760 310" width="100%" role="img" aria-labelledby="bridge-diagram-title bridge-diagram-description">
        <title id="bridge-diagram-title">Flux vérifié de Cortex Bridge</title>
        <desc id="bridge-diagram-description">{model.description}</desc>
        {model.edges.map((edge) => {
          const from = position.get(edge.from)!;
          const to = position.get(edge.to)!;
          return <g key={`${edge.from}-${edge.to}`}><line className="bd-edge" x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} /><line className="bd-pulse" x1={from[0]} y1={from[1]} x2={to[0]} y2={to[1]} /></g>;
        })}
        {model.nodes.map((node) => {
          const [x, y] = position.get(node.id)!;
          return <g className="bd-node" key={node.id} transform={`translate(${x - 72} ${y - 32})`}><rect width="144" height="64" rx="12" /><text className="bd-node-title" x="72" y="27">{node.label}</text><text className="bd-node-sub" x="72" y="47">{node.detail}</text></g>;
        })}
      </svg>
      <figcaption className="bridge-diagram-caption">Chaque action locale passe par un préflight explicite. Ollama est une branche optionnelle, jamais une promesse implicite.</figcaption>
    </figure>
  );
}
