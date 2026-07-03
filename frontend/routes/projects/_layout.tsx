import { define } from "../../utils.ts";
import { GitHubLink } from "../../components/GitHubLink.tsx";
import { Logo } from "../../components/Logo.tsx";
import ProjectDrawer from "../../islands/ProjectDrawer.tsx";
import ThemeToggle from "../../islands/ThemeToggle.tsx";

export default define.layout(function ProjectLayout({ Component }) {
  return (
    <div class="project-shell">
      <nav class="project-nav">
        <div class="nav-left">
          <ProjectDrawer />
          <a href="/" class="nav-wordmark">
            <Logo size={22} />
            FEDOT.MAS
          </a>
        </div>
        <div class="nav-right">
          <GitHubLink />
          <ThemeToggle />
        </div>
      </nav>
      <Component />
    </div>
  );
});
