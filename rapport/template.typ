// Mise en page et styles du rapport de stage.
//
// Tout ce qui relève de la forme est centralisé ici pour que les chapitres ne
// contiennent que du fond : numérotation des chapitres, légendes de figures et
// de tableaux au format « Figure 2.3 », listes automatiques, encadrés.

#let navy = rgb("#1a3a5c")
#let blue = rgb("#2e6da4")
#let teal = rgb("#2a9d8f")
#let amber = rgb("#e9a13b")
#let red = rgb("#c0504d")
#let grey = rgb("#5a6672")
#let light = rgb("#eef2f6")
#let border = rgb("#c8d2dc")


// ---------------------------------------------------------------- encadrés --

// Encadré neutre, pour une définition ou une mise en contexte.
#let encadre(titre, corps) = block(
  width: 100%,
  fill: light,
  stroke: (left: 3pt + blue),
  inset: 10pt,
  radius: 2pt,
  breakable: true,
)[
  #text(weight: "bold", fill: navy, size: 10pt)[#titre]
  #v(3pt)
  #text(size: 9.5pt)[#corps]
]

// Encadré d'avertissement : une limite, une réserve méthodologique, un piège.
#let reserve(titre, corps) = block(
  width: 100%,
  fill: rgb("#fdf6ec"),
  stroke: (left: 3pt + amber),
  inset: 10pt,
  radius: 2pt,
  breakable: true,
)[
  #text(weight: "bold", fill: rgb("#8a5a10"), size: 10pt)[#titre]
  #v(3pt)
  #text(size: 9.5pt)[#corps]
]

// À compléter par l'étudiant avant remise : ce qui ne peut pas être deviné.
#let a_completer(quoi) = box(
  fill: rgb("#fdecec"),
  stroke: 0.6pt + red,
  inset: (x: 4pt, y: 2pt),
  radius: 2pt,
)[#text(size: 9pt, fill: red)[à compléter : #quoi]]

// ------------------------------------------------------------------ tableau --

#let tableau(colonnes, entetes, lignes, largeurs: none) = {
  table(
    columns: if largeurs == none { colonnes } else { largeurs },
    stroke: 0.5pt + border,
    inset: 6pt,
    fill: (_, y) => if y == 0 { navy } else if calc.odd(y) { white } else { light },
    ..entetes.map(e => text(fill: white, weight: "bold", size: 9pt)[#e]),
    ..lignes.flatten().map(c => text(size: 9pt)[#c]),
  )
}

// ----------------------------------------------------------------- document --

#let rapport(
  titre: "",
  sous_titre: "",
  etudiant: "",
  encadrant_entreprise: "",
  encadrant_academique: "",
  organisme: "",
  periode: "",
  annee: "",
  corps,
) = {
  set document(title: titre, author: etudiant)
  set page(
    paper: "a4",
    margin: (top: 2.4cm, bottom: 2.4cm, left: 2.6cm, right: 2.2cm),
    numbering: none,
  )
  set text(lang: "fr", font: ("Times New Roman", "Liberation Serif", "DejaVu Serif"), size: 11pt)
  set par(justify: true, leading: 0.72em, first-line-indent: 1.2em)

  // titres numérotés « 1 », « 1.1 », « 1.1.1 »
  set heading(numbering: "1.1")
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    block(width: 100%)[
      #v(1.2cm)
      #text(size: 11pt, fill: blue, weight: "bold")[
        #if it.numbering != none [Chapitre #counter(heading).display("1")]
      ]
      #v(2pt)
      #text(size: 20pt, fill: navy, weight: "bold")[#it.body]
      #v(4pt)
      #line(length: 100%, stroke: 1.2pt + blue)
      #v(10pt)
    ]
  }
  // le numéro n'est affiché que si le titre est effectivement numéroté :
  // les sections des annexes et de l'introduction ne le sont pas
  show heading.where(level: 2): it => block(above: 16pt, below: 8pt)[
    #text(size: 13.5pt, fill: navy, weight: "bold")[
      #if it.numbering != none [#counter(heading).display() ]#it.body
    ]
  ]
  show heading.where(level: 3): it => block(above: 12pt, below: 6pt)[
    #text(size: 11.5pt, fill: blue, weight: "bold")[
      #if it.numbering != none [#counter(heading).display() ]#it.body
    ]
  ]

  // légendes : « Figure 2.3 — ... » et « Tableau 2.1 — ... ».
  // Le numéro de chapitre doit être lu au moment où la figure est posée, d'où
  // le `context` : sans lui, l'outline le résout à sa propre position et
  // affiche un numéro aberrant.
  set figure(numbering: "1")
  // « Fig. » par défaut : on impose les libellés attendus dans un rapport
  show figure.where(kind: image): set figure(supplement: [Figure])
  show figure.where(kind: table): set figure(supplement: [Tableau])
  show figure.caption: it => block(width: 90%)[
    #text(size: 9pt, fill: grey)[
      #text(weight: "bold", fill: navy)[
        #it.supplement #context it.counter.display(it.numbering)
      ] — #it.body
    ]
  ]
  set figure.caption(separator: [ ])
  show figure: set block(breakable: false)

  set table(stroke: 0.5pt + border)
  show link: it => text(fill: blue)[#it]
  show raw: set text(font: ("Consolas", "DejaVu Sans Mono"), size: 9pt)

  // ------------------------------------------------------- page de garde --
  page(numbering: none)[
    #set align(center)
    #v(0.6cm)
    #text(size: 13pt, weight: "bold")[République Tunisienne]
    #v(2pt)
    #text(size: 11pt)[Ministère de l'Enseignement Supérieur et de la Recherche Scientifique]
    #v(10pt)
    #text(size: 14pt, weight: "bold")[ESPRIT — École Supérieure Privée d'Ingénierie et de Technologies]
    #v(1.4cm)
    #line(length: 80%, stroke: 1pt + navy)
    #v(0.5cm)
    #text(size: 12pt, fill: grey, weight: "bold")[RAPPORT DE STAGE INGÉNIEUR]
    #v(0.4cm)
    #text(size: 21pt, weight: "bold", fill: navy)[#titre]
    #v(0.3cm)
    #text(size: 13pt, fill: grey)[#sous_titre]
    #v(0.5cm)
    #line(length: 80%, stroke: 1pt + navy)
    #v(1.6cm)

    #grid(
      columns: (1fr, 1fr),
      gutter: 20pt,
      align(left)[
        #text(weight: "bold")[Réalisé par :] \
        #etudiant
      ],
      align(left)[
        #text(weight: "bold")[Organisme d'accueil :] \
        #organisme
      ],
    )
    #v(0.8cm)
    #grid(
      columns: (1fr, 1fr),
      gutter: 20pt,
      align(left)[
        #text(weight: "bold")[Encadrant entreprise :] \
        #encadrant_entreprise
      ],
      align(left)[
        #text(weight: "bold")[Encadrant académique :] \
        #encadrant_academique
      ],
    )
    #v(1cm)
    #text(size: 11pt)[Période : #periode]
    #v(1fr)
    #text(size: 12pt, weight: "bold")[Année universitaire #annee]
    #v(0.5cm)
  ]

  // numérotation romaine pour les pages liminaires
  set page(numbering: "i")
  counter(page).update(1)

  corps
}
