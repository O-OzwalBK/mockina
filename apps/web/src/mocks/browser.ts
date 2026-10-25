import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

/** Browser mock worker; started only in dev with VITE_USE_MOCK=true. */
export const worker = setupWorker(...handlers);
