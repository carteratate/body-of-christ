import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TheoCorpus",
    short_name: "TheoCorpus",
    description:
      "Search Scripture, Church teaching, and two thousand years of Catholic writing. Find relevant passages and read them in context.",
    start_url: "/",
    display: "standalone",
    background_color: "#0D1828",
    theme_color: "#0D1828",
    icons: [
      {
        src: "/icons/theocorpus-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icons/theocorpus-512.png",
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}
