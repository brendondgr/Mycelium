import { appRedirect } from "@/lib/auth-server";

/** The Deadlines page became the Saves page; old links land there. */
export default async function DeadlinesPage() {
  await appRedirect("/app/saves");
}
