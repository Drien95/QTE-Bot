# QTE-Bot

Bot Windows pour les QTE de l'entraînement au combat (Garry's Mod, serveur EVO Bleach RP) :
détecte la case à l'écran, lit la lettre, appuie sur la touche ; peut enchaîner les sessions d'entraînement seul.

## Pour jouer (2 minutes)

1. **Dézippe** `QTE-Bot.zip` où tu veux, puis double-clique sur **`QTE-Bot.exe`**.
   Si Windows affiche « Windows a protégé votre ordinateur » : *Informations complémentaires* → *Exécuter quand même*
   (le programme n'est pas signé, c'est normal).
2. Mets Garry's Mod en **fenêtré sans bordure**, sur ton **écran principal**.
3. Dans le menu :
   - **Tuile QTE** (verte = allumée) : le bot appuie seul sur les touches des QTE. Touche **²** = pause.
   - **Tuile AUTOMATIQUE** : place-toi dans le cercle, katana en main, puis clique (ou **F7**).
     Le bot fait tout : E, choix de la difficulté, QTE, pause, et il recommence.
   - Clique sur les **pastilles colorées** pour choisir les difficultés jouées.
   - Carte **Touches** : clique sur une touche puis appuie sur celle que tu veux.
4. Fermer la fenêtre (ou **F10**) arrête tout. Tout réglage est enregistré automatiquement.

Le bot n'agit **que** si Garry's Mod est la fenêtre active, et s'arrête seul si le katana n'est pas en main,
si tu sors du cercle, ou à la limite de sessions/minutes.
En cas de souci : `qte_bot.log` et `captures/evenements.txt` disent ce que le bot a vu et fait.

> Automatiser un jeu en ligne est souvent interdit par le règlement des serveurs : vérifie le tien,
> c'est ton compte qui est en jeu.

## Pour développer

| Pour | Commande |
|---|---|
| Jouer (sans Python) | dézipper `QTE-Bot.zip`, lancer `QTE-Bot.exe` |
| Développer | `run.bat` (crée `.venv`, installe, lance le menu) |
| Fabriquer le zip | `build.bat` → `dist/QTE-Bot.zip` (tests obligatoires avant build) |
| Tests | `.venv\Scripts\python -m pytest -q` |

Options de `run.bat` : `--console` (sans menu), `--image <png>` (tester la détection sur une capture),
`--label` (étiqueter de nouvelles lettres capturées).

## Fonctionnement

```
capture écran (mss, ~37 img/s) ─► détection de la case ─► lecture de la lettre ─► décision d'appui ─► SendInput
                                    zone sombre fermée       comparaison aux        délai aléatoire,
                                    par un trait clair       modèles du jeu          réappui unique
```

- **Détection** (`detector.py`) : zones sombres entièrement fermées par un trait clair d'1 px, carrées, remplies
  à plus de 85 % (écarte le bouton rond « E » et le personnage).
- **Lecture** (`recognizer.py`) : corrélation avec les lettres réelles du jeu (`templates/*.png`), dessinées au
  pixel près identiques à chaque fois → score ≈ 1,00. Refus si score < 0,75 ou marge trop faible.
- **Appui** (`tracker.py`, `io_win.py`) : scancode selon la disposition **active** (AZERTY : `a` → touche A),
  délai tiré dans [min, max] depuis la 1re apparition, réappui unique si la case reste 150 ms après.
- **Automatisation** (`autopilot.py`) : automate « agir puis vérifier ».

```
ATTENTE ─E─► MENU (5 barres colorées) ─clic─► LANCEMENT ─1re case─► ENTRAÎNEMENT ─2,5 s sans case─► PAUSE ─┐
   ▲                                                                                                     │
   └─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
  Arrêt sur : message « katana », 3 échecs de suite, limite de sessions ou de minutes (jamais en pleine session).

## Performances (1080p, mesurées)

| | Avant | Maintenant |
|---|---|---|
| Capture d'une image | 23,5 ms (GDI) | ~2,4 ms (DXGI, repli GDI auto) |
| Détection de la case | 11 ms | 4,1 ms (recherche sur masque ½) |
| Images analysées/s | ~29–46 | ~60 (= rafraîchissement écran) |
| CPU, aucune case à l'écran | ~141 % d'un cœur | ~22 % |
| Fin de session détectée | 2,5 s après la dernière case | immédiate (dès la dernière case annoncée) |
| Clic sur la difficulté | 0,31 s | 0,16 s avec l'option ⚡ Turbo |

Écran inchangé (DXGI) = dernière analyse réutilisée ; aucune case depuis 2 s = 30 analyses/s ;
OpenCV en mono-thread (le multi-thread coûtait plus qu'il ne rapportait).
La capture de **sous-région** de `dxcam` fait planter Python : on capture toujours tout l'écran et on découpe.

## Sécurités

- Aucune touche ni clic si `game_process` (`gmod.exe`) n'est pas au premier plan.
- Instance unique (mutex Windows), relance = fenêtre existante ramenée devant.
- Touches et bouton souris toujours relâchés (`try/finally`), même sur erreur.
- Raccourcis refusés s'ils tombent sur une touche que le bot tape lui-même (sinon il se mettrait en pause seul).
- HUD exclu des captures d'écran (`WDA_EXCLUDEFROMCAPTURE`) : le bot ne voit jamais ses propres cadres.
- **Tests et scripts ne peuvent pas agir sur le jeu** : le moteur ne touche jamais l'écran, le clavier ou la
  souris lui-même, ils lui sont injectés (`GameIo`) ; seuls le menu et `--console` passent les vrais
  (`io_win.real_io()`), un moteur sans accès refuse de démarrer. En plus, `QTE_BOT_DRY_RUN=1` (posé
  automatiquement par `tests/conftest.py`) neutralise tout envoi au niveau de `SendInput`.
- Config écrite via fichier temporaire validé : jamais de `config.json` cassé ; journaux bornés à 1 Mo.

## Configuration (`config.json`)

Tout se règle depuis le menu (enregistrement automatique). Champs avancés, à la main :

| Champ | Rôle |
|---|---|
| `allowed_keys` | lettres de QTE possibles (`azeqsdwx`) |
| `min_score`, `min_margin` | seuils de lecture des lettres |
| `game_process` | exécutable du jeu (garde-fou premier plan) |
| `save_captures` | `true` = image annotée de chaque case dans `captures/` (diagnostic) |
| `roi` | fraction de l'écran principal surveillée |

## Hypothèses et limites connues

- Écran **principal** en **1080p** : la zone du message « katana » est en coordonnées 1080p.
- Jeu en fenêtré sans bordure (le HUD ne passe pas au-dessus d'un plein écran exclusif).
- XP comptée si toutes les cases de la session sont prises et que leur nombre atteint celui du menu
  (4/6/8/10/12) — déduit des captures, non confirmé côté serveur.
- Fin de session = 2,5 s sans case (cases espacées de ~0,9 s observées).
- Le jeu semble arrêter la session à la première case ratée ; délai min conseillé ≥ 120 ms.

## Nouvelles lettres

Si le jeu ajoute une lettre : l'ajouter à `allowed_keys`, activer `save_captures`, jouer quelques QTE,
puis `run.bat --label` pour transformer les lettres capturées en modèles.

## Structure

```
qte_bot/
  main.py          point d'entrée, instance unique, log
  engine.py        boucle temps réel (thread), stats, journal
  detector.py      case QTE        recognizer.py  lettres        tracker.py  quand appuyer
  autopilot.py     automate        auto_driver.py branchement     screen_ui.py menu / katana
  xp.py            compteur d'XP   hud.py/overlay.py HUD          io_win.py   écran, clavier, souris
  config.py        lecture/validation/écriture de config.json    keys.py     noms de touches
  ui/              thème et composants du menu                    gui.py      fenêtre
tests/             139 tests (vision sur vraies captures, automate, config, clavier…)
```
