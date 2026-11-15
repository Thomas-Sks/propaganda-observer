"use client";
import dynamic from "next/dynamic";

/* Intro (quelques secondes, une fois par session) : chargée côté client seulement, avec three.js. */
const Intro = dynamic(() => import("./Intro"), { ssr: false });
export default function IntroLoader() { return <Intro />; }
