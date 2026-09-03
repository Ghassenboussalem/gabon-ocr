// Recommendation letter — draft for Mariem Abcha (company supervisor) to
// review, personalize and sign.

#let navy = rgb("#1a3a5c")
#let grey = rgb("#5a6672")
#let border = rgb("#c8d2dc")

#set document(title: "Recommendation Letter — Ghassen Bousselem", author: "Mariem Abcha")
#set page(paper: "a4", margin: (top: 2.6cm, bottom: 2.6cm, left: 2.8cm, right: 2.8cm))
#set text(font: ("Calibri", "Carlito", "Arial", "Liberation Sans"), size: 11pt, lang: "en")
#set par(justify: true, leading: 0.68em)

// ------------------------------------------------------------- letterhead --
#align(center)[
  #text(size: 13pt, weight: "bold", fill: navy)[EY]
  #linebreak()
  #text(size: 9.5pt, fill: grey)[Tunis, Tunisia · ey.com]
]
#v(4pt)
#line(length: 100%, stroke: 0.8pt + border)
#v(14pt)

// ------------------------------------------------------------------- date --
#align(right)[Tunis, September 3, 2026]
#v(10pt)

#text(weight: "bold")[To Whom It May Concern]
#v(2pt)
#text(weight: "bold")[Subject: Recommendation Letter for Ghassen Bousselem]

#v(10pt)

I am writing to recommend Ghassen Bousselem for a final-year engineering
internship (Projet de Fin d'Études) abroad. I supervised Ghassen from 22 June
to 4 September 2026 during his internship at EY, where he worked
on a project applying vision-language models to civil registration document
processing and its integration with OpenCRVS, an open-source civil
registration and vital statistics platform used by several governments.

Over eleven weeks, Ghassen designed and built a document-extraction pipeline
covering twenty-seven African countries, capable of reading a scanned birth
certificate — regardless of its layout, language, or state of degradation —
and extracting its structured fields with an associated confidence score. He
then integrated this pipeline with OpenCRVS through two complementary paths:
its Event Notification API, and a scanning panel he added directly to the
declaration form itself, without modifying a single line of the platform's
core code. He backed this work with a rigorous, metrics-based evaluation of
extraction quality, using standard measures from the document-AI literature
(ANLS, character and word error rates, per-field precision and recall) rather
than relying on informal assessment.

What stood out most was Ghassen's autonomy and his engineering judgment. He
was capable of researching a technical domain from first principles, making
and justifying architectural decisions, diagnosing failures across a
multi-service infrastructure, and — notably — reporting the limitations of
his own work as carefully as its results. This last quality is one I value
particularly highly: an intern who documents what does not yet work, rather
than only what does, is one I trust to build systems intended for real,
sensitive use.

Ghassen combines strong technical skills with genuine intellectual honesty,
good communication, and the maturity to work independently on an open-ended
problem. I am confident he will bring the same qualities to a final-year
internship, and I recommend him without reservation.

I would be glad to answer any further questions.

#v(22pt)

Sincerely,

#v(30pt)

#grid(
  columns: (1fr, 1fr),
  align(left)[
    Mariem Abcha #linebreak()
    Assistant Manager, Technology, Strategy #sym.amp; Transformation #linebreak()
    EY
  ],
  align(right)[
    #v(38pt)
    #line(length: 55%, stroke: 0.6pt + border)
    #text(size: 9pt, fill: grey)[Signature and company stamp]
  ],
)
