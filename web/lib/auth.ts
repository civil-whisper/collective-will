import NextAuth, {type NextAuthConfig} from "next-auth";
import Credentials from "next-auth/providers/credentials";

export const authConfig: NextAuthConfig = {
  providers: [
    Credentials({
      name: "Email",
      credentials: {
        email: {label: "Email", type: "email"}
      },
      async authorize(credentials) {
        if (!credentials?.email) {
          return null;
        }
        return {id: String(credentials.email), email: String(credentials.email)};
      }
    })
  ],
  pages: {
    signIn: "/en/sign-in"
  },
  session: {strategy: "jwt"}
};

export const {handlers, auth, signIn, signOut} = NextAuth(authConfig);
