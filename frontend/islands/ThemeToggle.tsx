import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";

function initialTheme(): "light" | "dark" {
  if (typeof document === "undefined") return "light";
  try {
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || stored === "light") return stored;
  } catch (_) {
    // ignore
  }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function ThemeToggle() {
  const theme = useSignal<"light" | "dark">("light");

  useEffect(() => {
    theme.value = initialTheme();
    document.documentElement.dataset.theme = theme.value;
  }, []);

  function toggle() {
    const next = theme.value === "light" ? "dark" : "light";
    theme.value = next;
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch (_) {
      // ignore
    }
  }

  return (
    <button
      type="button"
      class="theme-toggle"
      onClick={toggle}
      aria-label={`Switch to ${
        theme.value === "light" ? "dark" : "light"
      } theme`}
      title={`Switch to ${theme.value === "light" ? "dark" : "light"} theme`}
    >
      {theme.value === "light" ? "☾" : "☀"}
    </button>
  );
}
