import { staticFile } from "remotion";

const REMOTE_ASSET_PREFIXES = ["http://", "https://", "data:"];

export function resolveAsset(src: string): string {
  if (REMOTE_ASSET_PREFIXES.some((prefix) => src.startsWith(prefix))) {
    return src;
  }

  const normalized = src.replace(/\\/g, "/");
  if (normalized.startsWith("file://")) {
    const pathPart = normalized.slice("file://".length);
    if (pathPart.startsWith("/")) {
      const absolutePath = pathPart.replace(/^\/+/, "/");
      return `file://${encodeURI(absolutePath)}`;
    }
    return encodeURI(normalized);
  }

  if (normalized.startsWith("/")) {
    return `file://${encodeURI(normalized)}`;
  }
  if (/^[A-Za-z]:\//.test(normalized)) {
    return `file:///${encodeURI(normalized)}`;
  }
  return staticFile(normalized);
}
