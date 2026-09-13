import type { SVGProps } from "react";
import {
  Search, Plus, Settings2, Menu, PanelRight, MessageSquarePlus, NotebookTabs, Pin, Ellipsis, Send, Square, Pause, Play, Check, CheckCheck, Clock3, Activity, Globe, ShieldCheck, Folder, SquareTerminal, PanelsTopLeft, Camera, Database, Cpu, List, Archive, ChevronDown, ChevronRight, X, Paperclip, Sparkles, RefreshCw, ExternalLink, TriangleAlert, Eye, ArchiveX, Download, Copy, Info, PanelLeftClose,
  type LucideIcon,
} from "lucide-react";

// Lucide geometry (ISC). Local CSS motion; no remote icons or animation runtime.
export type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
  busy?: boolean;
  confirmed?: boolean;
};

function cortexIcon(Glyph: LucideIcon, motion = "") {
  return function CortexIcon({ size = 20, className = "", busy = false, confirmed = false, ...props }: IconProps) {
    return <Glyph {...props} size={size} strokeWidth={1.8} aria-hidden="true" focusable="false"
      className={["cortex-icon", motion, className, busy ? "is-busy" : "", confirmed ? "is-confirmed" : ""].filter(Boolean).join(" ")} />;
  };
}

export const SearchIcon = cortexIcon(Search);
export const PlusIcon = cortexIcon(Plus);
export const SettingsIcon = cortexIcon(Settings2);
export const MenuIcon = cortexIcon(Menu);
export const PanelIcon = cortexIcon(PanelRight);
export const MessageIcon = cortexIcon(MessageSquarePlus);
export const ProjectIcon = cortexIcon(NotebookTabs);
export const PinIcon = cortexIcon(Pin);
export const MoreIcon = cortexIcon(Ellipsis);
export const SendIcon = cortexIcon(Send, "icon-send");
export const StopIcon = cortexIcon(Square);
export const PauseIcon = cortexIcon(Pause);
export const PlayIcon = cortexIcon(Play);
export const CheckIcon = cortexIcon(Check, "icon-check");
export const DoubleCheckIcon = cortexIcon(CheckCheck);
export const ClockIcon = cortexIcon(Clock3);
export const ActivityIcon = cortexIcon(Activity);
export const GlobeIcon = cortexIcon(Globe);
export const ShieldIcon = cortexIcon(ShieldCheck);
export const FolderIcon = cortexIcon(Folder);
export const TerminalIcon = cortexIcon(SquareTerminal);
export const BrowserIcon = cortexIcon(PanelsTopLeft);
export const CameraIcon = cortexIcon(Camera);
export const DatabaseIcon = cortexIcon(Database);
export const CpuIcon = cortexIcon(Cpu);
export const ListIcon = cortexIcon(List);
export const ArchiveIcon = cortexIcon(Archive);
export const ChevronDownIcon = cortexIcon(ChevronDown, "icon-chevron");
export const ChevronRightIcon = cortexIcon(ChevronRight, "icon-chevron");
export const XIcon = cortexIcon(X);
export const PaperclipIcon = cortexIcon(Paperclip);
export const SparkIcon = cortexIcon(Sparkles);
export const RefreshIcon = cortexIcon(RefreshCw, "icon-refresh");
export const ExternalLinkIcon = cortexIcon(ExternalLink);
export const AlertIcon = cortexIcon(TriangleAlert);
export const EyeIcon = cortexIcon(Eye);
export const TrashBlockedIcon = cortexIcon(ArchiveX);
export const DownloadIcon = cortexIcon(Download);
export const CopyIcon = cortexIcon(Copy);
export const InfoIcon = cortexIcon(Info);
export const CollapseIcon = cortexIcon(PanelLeftClose);
