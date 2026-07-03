import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

interface Project {
  id: string;
  title: string;
  updatedAt: string;
}

interface ProjectDrawerProps {
  initialProjects?: Project[];
  currentProjectId?: string;
}

export default function ProjectDrawer(
  { initialProjects, currentProjectId }: ProjectDrawerProps,
) {
  const open = useSignal(false);
  const projects = useSignal<Project[] | null>(
    initialProjects ?? null,
  );
  const error = useSignal("");

  async function load() {
    if (initialProjects) return;
    try {
      const res = await fetch("/api/projects");
      if (!res.ok) throw new Error("Failed to load projects");
      projects.value = await res.json();
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function toggle() {
    open.value = !open.value;
  }

  function close() {
    open.value = false;
  }

  return (
    <>
      <button
        type="button"
        class="drawer-toggle"
        onClick={toggle}
        aria-label="Projects"
        title="Projects"
      >
        ☰
      </button>

      {open.value && (
        <>
          <div class="drawer-overlay" onClick={close} />
          <aside class="drawer-panel">
            <div class="drawer-head">
              <span>Projects</span>
              <button
                type="button"
                class="close-btn"
                onClick={close}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <form
              method="post"
              action="/"
              class="drawer-create"
              f-client-nav={false}
            >
              <input
                name="title"
                placeholder="Title (optional)..."
                autocomplete="off"
              />
              <button type="submit">+</button>
            </form>

            {error.value && <p class="drawer-error">{error.value}</p>}

            <div class="drawer-list">
              {projects.value === null
                ? <span class="drawer-empty">Loading...</span>
                : projects.value.length === 0
                ? <span class="drawer-empty">No projects yet.</span>
                : projects.value.map((p) => (
                  <div
                    key={p.id}
                    class={`drawer-project ${
                      p.id === currentProjectId ? "current" : ""
                    }`}
                  >
                    <a
                      href={`/projects/${p.id}`}
                      class="drawer-title"
                      onClick={close}
                    >
                      {p.title}
                    </a>
                    <div class="drawer-actions">
                      <a
                        href={`/projects/${p.id}/rename`}
                        class="icon-btn"
                        aria-label="Rename"
                        title="Rename"
                        onClick={close}
                      >
                        ✎
                      </a>
                      <form
                        method="post"
                        action={`/projects/${p.id}/delete`}
                        f-client-nav={false}
                      >
                        <button
                          type="submit"
                          class="icon-btn danger"
                          aria-label="Delete"
                          title="Delete"
                        >
                          ×
                        </button>
                      </form>
                    </div>
                  </div>
                ))}
            </div>

            <a href="/" class="drawer-home" onClick={close}>
              Welcome
            </a>
          </aside>
        </>
      )}
    </>
  );
}
