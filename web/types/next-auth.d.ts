import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    backendAccessToken?: string;
  }

  interface User {
    backendAccessToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendAccessToken?: string;
  }
}
