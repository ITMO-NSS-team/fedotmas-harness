import { createDefine } from "fresh";

export interface State {
  session: string;
}

export const define = createDefine<State>();
