/** Minimal history-API router; the server serves index.html for every path. */
class Router {
  path = $state(window.location.pathname);

  constructor() {
    window.addEventListener("popstate", () => (this.path = window.location.pathname));
  }

  go(path: string) {
    if (path === this.path) return;
    history.pushState(null, "", path);
    this.path = path;
  }
}

export const router = new Router();

/** Use on `<a>` clicks so plain left-clicks navigate in-app. */
export function link(event: MouseEvent) {
  const anchor = event.currentTarget as HTMLAnchorElement;
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  router.go(anchor.pathname);
}
