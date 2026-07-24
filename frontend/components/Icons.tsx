import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function iconProps({ size = 18, ...props }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
}

export function SearchIcon(props: IconProps) {
  return <svg {...iconProps(props)}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.4-3.4"/></svg>;
}
export function PlusIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M12 5v14M5 12h14"/></svg>;
}
export function SettingsIcon(props: IconProps) {
  return <svg {...iconProps(props)}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.12 2.12-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56V20h-3v-.09a1.7 1.7 0 0 0-1.08-1.55 1.7 1.7 0 0 0-1.88.34l-.06.06-2.12-2.12.06-.06A1.7 1.7 0 0 0 7 14.7a1.7 1.7 0 0 0-1.56-1.03H5v-3h.09A1.7 1.7 0 0 0 6.64 9.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.12-2.12.06.06A1.7 1.7 0 0 0 10.3 6a1.7 1.7 0 0 0 1.03-1.56V4h3v.09a1.7 1.7 0 0 0 1.08 1.55 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.12 2.12-.06.06A1.7 1.7 0 0 0 19 9.3a1.7 1.7 0 0 0 1.56 1.03H21v3h-.09A1.7 1.7 0 0 0 19.4 15Z"/></svg>;
}
export function MenuIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M4 7h16M4 12h16M4 17h16"/></svg>;
}
export function PanelIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/></svg>;
}
export function MessageIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"/></svg>;
}
export function ProjectIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H18a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6.5A2.5 2.5 0 0 1 4 18.5Z"/><path d="M8 3v18M11 8h5M11 12h5"/></svg>;
}
export function PinIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m15 4 5 5-3 2v4l-3 3-4-4-5 5-1-1 5-5-4-4 3-3h4Z"/></svg>;
}
export function MoreIcon(props: IconProps) {
  return <svg {...iconProps(props)}><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></svg>;
}
export function SendIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>;
}
export function StopIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="6" y="6" width="12" height="12" rx="2"/></svg>;
}
export function PauseIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M9 5v14M15 5v14"/></svg>;
}
export function PlayIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m8 5 11 7-11 7Z"/></svg>;
}
export function CheckIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m5 12 4 4L19 6"/></svg>;
}
export function DoubleCheckIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m2 12 4 4L16 6"/><path d="m9 15 2 2L22 6"/></svg>;
}
export function ClockIcon(props: IconProps) {
  return <svg {...iconProps(props)}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
}
export function ActivityIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M3 12h4l2-7 4 14 2-7h6"/></svg>;
}
export function GlobeIcon(props: IconProps) {
  return <svg {...iconProps(props)}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>;
}
export function ShieldIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M12 3 4.5 6v5.5c0 4.8 3.1 8.1 7.5 9.5 4.4-1.4 7.5-4.7 7.5-9.5V6Z"/><path d="m9 12 2 2 4-4"/></svg>;
}
export function FolderIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3Z"/></svg>;
}
export function TerminalIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/></svg>;
}
export function BrowserIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/></svg>;
}
export function CameraIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M4 8h3l1.5-2h7L17 8h3a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z"/><circle cx="12" cy="14" r="3"/></svg>;
}
export function DatabaseIcon(props: IconProps) {
  return <svg {...iconProps(props)}><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>;
}
export function CpuIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/><rect x="10" y="10" width="4" height="4" rx=".5"/></svg>;
}
export function ListIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></svg>;
}
export function ArchiveIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M3 5h18v4H3zM5 9v11h14V9M9 13h6"/></svg>;
}
export function ChevronDownIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m6 9 6 6 6-6"/></svg>;
}
export function ChevronRightIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m9 18 6-6-6-6"/></svg>;
}
export function XIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M6 6l12 12M18 6 6 18"/></svg>;
}
export function PaperclipIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m21.4 11.6-8.9 8.9a6 6 0 0 1-8.5-8.5l9.4-9.4a4 4 0 0 1 5.7 5.7l-9.4 9.4a2 2 0 0 1-2.8-2.8l8.7-8.7"/></svg>;
}
export function SparkIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m12 3 1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8ZM5 14l.8 2.2L8 17l-2.2.8L5 20l-.8-2.2L2 17l2.2-.8Z"/></svg>;
}
export function RefreshIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 8A7 7 0 0 1 18 6l2 6M18 16a7 7 0 0 1-11.9 2L4 12"/></svg>;
}
export function ExternalLinkIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/></svg>;
}
export function AlertIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M10.3 3.7 2.5 17.2A2 2 0 0 0 4.2 20h15.6a2 2 0 0 0 1.7-2.8L13.7 3.7a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>;
}
export function EyeIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>;
}
export function TrashBlockedIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14"/><path d="m5 5 14 14"/></svg>;
}
export function DownloadIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>;
}
export function CopyIcon(props: IconProps) {
  return <svg {...iconProps(props)}><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 9V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h4"/></svg>;
}
