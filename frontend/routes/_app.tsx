import { define } from "../utils.ts";
import { Partial } from "fresh/runtime";

const THEME_INIT = `
(function(){
  try {
    var t = localStorage.getItem('theme');
    var dark = t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    if (dark) document.documentElement.dataset.theme = 'dark';
  } catch (_) {}
})();
`;

export default define.page(function App({ Component }) {
  return (
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>FEDOT.MAS</title>
        <link rel="icon" type="image/svg+xml" href="/logo.svg" />
        <script>{THEME_INIT}</script>
      </head>
      <body f-client-nav>
        <Partial name="body">
          <Component />
        </Partial>
      </body>
    </html>
  );
});
