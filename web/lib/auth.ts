import NextAuth, {type NextAuthConfig} from "next-auth";
import Credentials from "next-auth/providers/credentials";
import {resolveServerApiBase} from "@/lib/auth-config";

const API_BASE = resolveServerApiBase();

export const authConfig: NextAuthConfig = {
  providers: [
    Credentials({
      name: "Email",
      credentials: {
        email: {label: "Email", type: "email"},
        webSessionCode: {label: "Web Session Code", type: "text"},
      },
      async authorize(credentials) {
        const email = typeof credentials?.email === "string" ? credentials.email : "";
        const code = typeof credentials?.webSessionCode === "string" ? credentials.webSessionCode : "";
        if (!email || !code) {
          return null;
        }
        const response = await fetch(`${API_BASE}/auth/web-session`, {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({email, code}),
          cache: "no-store",
        });
        if (!response.ok) {
          return null;
        }
        const payload = (await response.json()) as {
          email?: string;
          access_token?: string;
        };
        if (!payload.email || !payload.access_token) {
          return null;
        }
        return {
          id: payload.email,
          email: payload.email,
          backendAccessToken: payload.access_token,
        };
      }
    })
  ],
  pages: {
    signIn: "/en/sign-in"
  },
  session: {strategy: "jwt"},
  callbacks: {
    async jwt({token, user}) {
      if (user && "backendAccessToken" in user) {
        token.backendAccessToken = String(user.backendAccessToken);
      }
      return token;
    },
    async session({session, token}) {
      if (session.user?.email && token.backendAccessToken) {
        session.backendAccessToken = String(token.backendAccessToken);
      }
      return session;
    },
  },
};

export const {handlers, auth, signIn, signOut} = NextAuth(authConfig);
