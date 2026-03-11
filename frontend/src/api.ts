// API configuration - use relative path to go through Vite proxy
const getBasePath = () => {
  // Always use relative path - Vite proxy handles routing
  return "";
};

export const API_BASE = getBasePath();

export const apiUrl = (path: string): string => {
  // Remove leading slash if present
  const cleanPath = path.startsWith("/") ? path.slice(1) : path;
  return `/cfd/api/${cleanPath}`;
};
