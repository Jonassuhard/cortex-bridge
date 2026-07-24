"use client";

import { useMemo, useState } from "react";
import type { ConversationSummary } from "@/lib/types";
import {
  ArchiveIcon,
  ChevronDownIcon,
  MessageIcon,
  MoreIcon,
  PinIcon,
  PlusIcon,
  ProjectIcon,
  RefreshIcon,
  SearchIcon,
  SettingsIcon,
} from "./Icons";
import { CortexLogo } from "./CortexLogo";

interface ConversationSidebarProps {
  conversations: ConversationSummary[];
  selectedUrl: string | null;
  loading: boolean;
  collapsed: boolean;
  onCollapse: () => void;
  onSelect: (conversation: ConversationSummary) => void;
  onRefresh: () => void;
  onNewConversation: () => void;
  onNewMission: () => void;
  onOpenSettings: () => void;
}

function statusClass(status?: ConversationSummary["status"]) {
  if (status === "generating" || status === "mission") return "is-active";
  if (status === "approval") return "is-warning";
  if (status === "blocked" || status === "error") return "is-error";
  return "is-idle";
}

export function ConversationSidebar({
  conversations,
  selectedUrl,
  loading,
  collapsed,
  onCollapse,
  onSelect,
  onRefresh,
  onNewConversation,
  onNewMission,
  onOpenSettings,
}: ConversationSidebarProps) {
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const source = normalized
      ? conversations.filter((conversation) =>
          `${conversation.title} ${conversation.preview || ""}`.toLowerCase().includes(normalized),
        )
      : conversations;
    return showAll ? source : source.slice(0, 12);
  }, [conversations, query, showAll]);

  if (collapsed) {
    return (
      <aside className="conversation-sidebar is-collapsed" aria-label="Navigation conversations">
        <button className="sidebar-logo-button" onClick={onCollapse} title="Déplier la barre latérale">
          <CortexLogo compact />
        </button>
        <button className="sidebar-icon-button" onClick={onNewConversation} title="Nouvelle conversation"><PlusIcon /></button>
        <button className="sidebar-icon-button" onClick={onNewMission} title="Nouvelle mission"><ProjectIcon /></button>
        <div className="collapsed-spacer" />
        <button className="sidebar-icon-button" onClick={onOpenSettings} title="Paramètres"><SettingsIcon /></button>
      </aside>
    );
  }

  return (
    <aside className="conversation-sidebar" aria-label="Conversations ChatGPT">
      <div className="sidebar-brand-row">
        <CortexLogo />
        <div className="sidebar-brand-actions">
          <button className="icon-button" onClick={onRefresh} title="Actualiser les conversations" aria-label="Actualiser les conversations">
            <RefreshIcon className={loading ? "spin-slow" : ""} />
          </button>
          <button className="icon-button" onClick={onCollapse} title="Réduire la barre latérale" aria-label="Réduire la barre latérale">
            <span className="collapse-glyph">—</span>
          </button>
        </div>
      </div>

      <div className="sidebar-primary-actions">
        <button className="sidebar-action is-primary" onClick={onNewConversation}>
          <MessageIcon />
          <span>Nouveau chat</span>
          <kbd>⌘N</kbd>
        </button>
        <button className="sidebar-action" onClick={onNewMission}>
          <ProjectIcon />
          <span>Nouvelle mission</span>
        </button>
      </div>

      <div className="conversation-search-wrap">
        <SearchIcon size={16} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Rechercher dans les chats"
          aria-label="Rechercher dans les conversations"
        />
        {query && <button onClick={() => setQuery("")} aria-label="Effacer la recherche">×</button>}
      </div>

      <div className="sidebar-section-head">
        <span>{query ? "Résultats" : "Conversations"}</span>
        <span className="sidebar-count">{conversations.length}</span>
      </div>

      <div className="conversation-list" role="listbox" aria-label="Liste des conversations">
        {loading && conversations.length === 0 && (
          <div className="conversation-skeletons" aria-label="Chargement des conversations">
            {Array.from({ length: 7 }).map((_, index) => <div className="conversation-skeleton" key={index} />)}
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="sidebar-empty-state">
            <SearchIcon size={19} />
            <p>Aucune conversation trouvée.</p>
          </div>
        )}
        {filtered.map((conversation) => {
          const selected = selectedUrl === conversation.url;
          return (
            <button
              key={conversation.identity || conversation.url}
              className={`conversation-row ${selected ? "is-selected" : ""}`}
              onClick={() => onSelect(conversation)}
              role="option"
              aria-selected={selected}
            >
              <span className={`conversation-status ${statusClass(conversation.status)}`} />
              <span className="conversation-copy">
                <span className="conversation-title-line">
                  <strong>{conversation.title || "Conversation sans titre"}</strong>
                  <time>{conversation.timestamp || ""}</time>
                </span>
                <span className="conversation-preview">{conversation.preview || "Ouvrir la conversation"}</span>
              </span>
              <span className="conversation-meta">
                {conversation.pinned && <PinIcon size={13} />}
                {!!conversation.unread && <span className="unread-badge">{conversation.unread}</span>}
              </span>
            </button>
          );
        })}
      </div>

      {conversations.length > 12 && !query && (
        <button className="show-more-button" onClick={() => setShowAll((value) => !value)}>
          <MoreIcon />
          <span>{showAll ? "Afficher moins" : "Voir plus"}</span>
          <ChevronDownIcon className={showAll ? "is-rotated" : ""} size={15} />
        </button>
      )}

      <button className="archived-button">
        <ArchiveIcon size={16} />
        <span>Conversations archivées</span>
      </button>

      <div className="sidebar-bottom">
        <button className="settings-entry" onClick={onOpenSettings}>
          <span className="settings-entry-icon"><SettingsIcon /></span>
          <span className="settings-entry-copy"><strong>Paramètres</strong><small>Modèles, permissions, transport</small></span>
          <ChevronDownIcon size={15} />
        </button>
        <div className="account-row">
          <span className="account-avatar">JS</span>
          <span><strong>Jonas Suhard</strong><small>Local · ChatGPT Pro</small></span>
        </div>
      </div>
    </aside>
  );
}
