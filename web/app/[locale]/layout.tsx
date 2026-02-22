import {ReactNode} from "react";
import {NextIntlClientProvider} from "next-intl";
import {getMessages} from "next-intl/server";

import {NavBar} from "@/components/NavBar";
import "../globals.css";

type Props = {
  children: ReactNode;
  params: Promise<{locale: "fa" | "en"}>;
};

export default async function LocaleLayout({children, params}: Props) {
  const {locale} = await params;
  const messages = await getMessages();
  const direction = locale === "fa" ? "rtl" : "ltr";

  return (
    <html lang={locale} dir={direction}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <NavBar />
          <main>{children}</main>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
