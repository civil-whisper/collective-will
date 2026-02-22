import {getRequestConfig} from "next-intl/server";
import {routing} from "./routing";

export default getRequestConfig(async ({locale}) => {
  const resolvedLocale = routing.locales.includes(locale as "fa" | "en")
    ? locale
    : routing.defaultLocale;
  return {
    locale: resolvedLocale,
    messages: (await import(`../messages/${resolvedLocale}.json`)).default
  };
});
