import {auth} from "@/lib/auth";
import {redirect} from "next/navigation";

export async function requireAuth() {
  const session = await auth();
  if (!session?.user) {
    redirect("/en/sign-in");
  }
  return session;
}
