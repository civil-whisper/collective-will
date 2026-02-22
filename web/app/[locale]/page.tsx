import {useTranslations} from "next-intl";
import Link from "next/link";

import {SubscribeForm} from "@/components/SubscribeForm";

export default function LandingPage() {
  const t = useTranslations("landing");
  const nav = useTranslations("nav");

  return (
    <div>
      <section style={{textAlign: "center", padding: "4rem 1rem"}}>
        <h1 style={{fontSize: "2rem", marginBottom: "1rem"}}>{t("headline")}</h1>
        <p style={{fontSize: "1.2rem", marginBottom: "2rem"}}>{t("subtitle")}</p>
        <SubscribeForm />
      </section>

      <section style={{padding: "2rem 1rem"}}>
        <h2>{t("howItWorks")}</h2>
        <ol style={{listStyle: "decimal", paddingInlineStart: "2rem"}}>
          <li>{t("step1")}</li>
          <li>{t("step2")}</li>
          <li>{t("step3")}</li>
          <li>{t("step4")}</li>
        </ol>
      </section>

      <section style={{padding: "2rem 1rem"}}>
        <SubscribeForm />
      </section>

      <section style={{padding: "2rem 1rem"}}>
        <h2>{t("trustTitle")}</h2>
        <p>{t("trustDescription")}</p>
        <Link href="./analytics/evidence">{nav("audit")}</Link>
      </section>
    </div>
  );
}
