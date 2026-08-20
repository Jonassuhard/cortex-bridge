"use client";

import { useMemo, useState } from "react";
import type { ConversationSummary } from "@/lib/types";
import { groupConversations } from "@/lib/conversations";
import {
  ArchiveIcon,
  ChevronDownIcon,
  MenuIcon,
  MessageIcon,
  GlobeIcon,
  PinIcon,
  PlusIcon,
  RefreshIcon,
  SearchIcon,
  SettingsIcon,
} from "./Icons";
import { CortexLogo } from "./CortexLogo";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  selectedKey: string | null;
  loading: boolean;
  collapsed: boolean;
  onCollapse: () => void;
  onSelect: (conversation: ConversationSummary) => void;
  onRefresh: () => void;
  onNewConversation: () => void;
  onOpenSettings: () => void;
}

function formatTimestamp(value?: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const now = new Date();
  if (parsed.toDateString() === now.toDateString()) {
    return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(parsed);
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (parsed.toDateString() === yesterday.toDateString()) return "Hier";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" })
    .format(parsed)
    .replace(/\.$/u, "");
}

function ConversationRow({ conversation, selectedKey, onSelect }: {
  conversation: ConversationSummary;
  selectedKey: string | null;
  onSelect: (conversation: ConversationSummary) => void;
}) {
  const selected = selectedKey === conversation.identity;
  return (
    <button
      className={`conversation-row ${selected ? "is-selected" : ""}`}
      onClick={() => onSelect(conversation)}
      aria-current={selected ? "page" : undefined}
    >
      <span className={`conversation-status ${conversation.status === "error" || conversation.status === "blocked" ? "is-error" : conversation.status && conversation.status !== "idle" ? "is-active" : "is-idle"}`} />
      <span className="conversation-copy">
        <span className="conversation-title-line"><strong>{conversation.title || "Conversation sans titre"}</strong><time dateTime={conversation.timestamp}>{formatTimestamp(conversation.timestamp)}</time></span>
        <span className="conversation-preview">{conversation.preview || "Ouvrir la conversation"}</span>
        <span className="conversation-subline">
          {conversation.sync_state === "stale" && <span className="conv-sync-state" title={conversation.sync_error || "Synchronisation en échec"}>Cache obsolète</span>}
          {typeof conversation.message_count === "number" && <span className="conv-count">{conversation.message_count} message{conversation.message_count > 1 ? "s" : ""}</span>}
        </span>
      </span>
      <span className="conversation-meta">{conversation.pinned && <PinIcon size={13} />}{!!conversation.unread && <span className="unread-badge">{conversation.unread}</span>}</span>
    </button>
  );
}

export function ConversationSidebar({ conversations, selectedKey, loading, collapsed, onCollapse, onSelect, onRefresh, onNewConversation, onOpenSettings }: ConversationSidebarProps) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return normalized
      ? conversations.filter((conversation) => `${conversation.title} ${conversation.preview || ""}`.toLowerCase().includes(normalized))
      : conversations;
  }, [conversations, query]);
  const groups = useMemo(() => groupConversations(filtered, 50), [filtered]);

  if (collapsed) {
    return (
      <aside className="conversation-sidebar is-collapsed" aria-label="Navigation conversations">
        <button className="sidebar-icon-button unfold-button" onClick={onCollapse} title="Déplier" aria-label="Déplier"><MenuIcon /></button>
        <button className="sidebar-icon-button" onClick={onNewConversation} title="Nouvelle conversation" aria-label="Nouvelle conversation"><PlusIcon /></button>
        <nav aria-label="Conversations récentes" className="collapsed-conversations">
          {[...groups.pinned, ...groups.projects.flatMap((group) => group.items), ...groups.recent].slice(0, 5).map((conversation) => (
            <button key={conversation.identity} className={`sidebar-icon-button ${selectedKey === conversation.identity ? "is-active" : ""}`} onClick={() => onSelect(conversation)} title={conversation.title} aria-label={conversation.title}><MessageIcon /></button>
          ))}
        </nav>
        <div className="collapsed-spacer" />
        <button className="sidebar-icon-button" onClick={onOpenSettings} title="Paramètres" aria-label="Paramètres"><SettingsIcon /></button>
      </aside>
    );
  }

  const renderGroup = (title: string, items: ConversationSummary[]) => items.length > 0 && (
    <section className="conversation-group" key={title}>
      <h2>{title}</h2>
      {items.map((conversation) => <ConversationRow key={conversation.identity} conversation={conversation} selectedKey={selectedKey} onSelect={onSelect} />)}
    </section>
  );

  return (
    <aside className="conversation-sidebar" aria-label="Conversations ChatGPT">
      <div className="sidebar-brand-row">
        <CortexLogo />
        <div className="sidebar-brand-actions">
          <button className="icon-button" onClick={onRefresh} title="Actualiser les conversations" aria-label="Actualiser les conversations"><RefreshIcon className={loading ? "spin-slow" : ""} /></button>
          <button className="icon-button" onClick={onCollapse} title="Réduire la barre latérale" aria-label="Réduire la barre latérale"><span className="collapse-glyph">—</span></button>
        </div>
      </div>
      <div className="sidebar-primary-actions">
        <button className="sidebar-action is-primary" onClick={onNewConversation}><MessageIcon /><span>Nouvelle conversation</span><kbd>⌘N</kbd></button>
      </div>
      <div className="conversation-search-wrap">
        <SearchIcon size={16} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher dans les conversations" aria-label="Rechercher dans les conversations" />
        {query && <button onClick={() => setQuery("")} aria-label="Effacer la recherche">×</button>}
      </div>
      <nav className="conversation-list" aria-label="Liste des conversations">
        {loading && conversations.length === 0 && <div className="conversation-skeletons" aria-label="Chargement des conversations">{Array.from({ length: 7 }).map((_, index) => <div className="conversation-skeleton" key={index} />)}</div>}
        {!loading && filtered.length === 0 && <div className="sidebar-empty-state"><GlobeIcon size={19} /><p>{query ? "Aucune conversation trouvée." : "Aucune conversation synchronisée."}</p></div>}
        {renderGroup("Épinglées", groups.pinned)}
        {groups.projects.map((group) => renderGroup(group.title, group.items))}
        {renderGroup("Récentes", groups.recent)}
      </nav>
      <button className="archived-button"><ArchiveIcon size={16} /><span>Conversations archivées</span></button>
      <div className="sidebar-bottom">
        <button className="settings-entry" onClick={onOpenSettings}><span className="settings-entry-icon"><SettingsIcon /></span><span className="settings-entry-copy"><strong>Paramètres</strong><small>Modèles, permissions, transport</small></span><ChevronDownIcon size={15} /></button>
        <div className="account-row"><span className="account-avatar">CL</span><span><strong>Compte local</strong><small>Session locale</small></span></div>
      </div>
    </aside>
  );
}
