import localFont from "next/font/local";

// Solo los shells público/auth importan estas fuentes. La app conserva su sans.
export const publicSans = localFont({
  src: "../app/fonts/Manrope-Variable.ttf",
  weight: "200 800",
  display: "swap",
  preload: true,
});

export const publicEditorial = localFont({
  src: "../app/fonts/InstrumentSerif.ttf",
  variable: "--font-editorial",
  weight: "400",
  display: "swap",
  preload: true,
});
