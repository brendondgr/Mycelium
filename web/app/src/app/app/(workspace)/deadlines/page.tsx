import { redirect } from "next/navigation";

/** The Deadlines page became the Saves page; old links land there. */
export default function DeadlinesPage() {
  redirect("/app/saves");
}
