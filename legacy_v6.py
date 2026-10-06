import json
import math
import random
import threading
import tkinter as tk
from tkinter import ttk
import urllib.request

APP_TITLE = "AFFENKÄFIG"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b"

AXES = [
    "progressivitaet", "oekologie", "sozialstaat", "staat_markt",
    "international", "liberalitaet", "wirtschaftswachstum"
]
AXIS_LABELS = {
    "progressivitaet": "Progressivität",
    "oekologie": "Ökologie",
    "sozialstaat": "Sozialstaat",
    "staat_markt": "Staat ↔ Markt",
    "international": "Internationalität",
    "liberalitaet": "Liberalität",
    "wirtschaftswachstum": "Wirtschaftswachstum",
}

# These are deliberately stylized simulation parameters, not measurements of real parties.
PARTIES = {
    # Simulation parameters only; they are not measurements of real parties.
    "CDU/CSU": {"color": "#68727c", "seats": 21,
        "values": {"progressivitaet":20,"oekologie":-10,"sozialstaat":0,"staat_markt":100,"international":55,"liberalitaet":35,"wirtschaftswachstum":100}},
    "AfD": {"color": "#5578a8", "seats": 15,
        "values": {"progressivitaet":-100,"oekologie":-100,"sozialstaat":-20,"staat_markt":100,"international":-100,"liberalitaet":-10,"wirtschaftswachstum":100}},
    "SPD": {"color": "#b64c5a", "seats": 12,
        "values": {"progressivitaet":100,"oekologie":100,"sozialstaat":100,"staat_markt":-15,"international":100,"liberalitaet":45,"wirtschaftswachstum":55}},
    "Bündnis 90/Die Grünen": {"color": "#6b9550", "seats": 9,
        "values": {"progressivitaet":100,"oekologie":100,"sozialstaat":65,"staat_markt":-30,"international":100,"liberalitaet":100,"wirtschaftswachstum":35}},
    "Die Linke": {"color": "#9a5682", "seats": 6,
        "values": {"progressivitaet":100,"oekologie":100,"sozialstaat":100,"staat_markt":-100,"international":100,"liberalitaet":90,"wirtschaftswachstum":-25}},
}

FIRST_NAMES = ["Anna","Max","Lea","Jonas","Mia","Paul","Nina","Felix","Lina","Ben","Clara","Elias","Laura","Noah","Sophie","Leon","Emma","Jan","Hannah","Tim","Marie","David"]
LAST_NAMES = ["Weber","Schneider","Fischer","Wagner","Becker","Hoffmann","Schulz","Koch","Bauer","Richter","Klein","Wolf","Neumann","Schwarz","Zimmermann","Braun","Krüger","Hartmann","Lange","Krause","Meyer","Vogel","Franke","Busch"]
PERSONALITIES = ["ruhig und analytisch","konfrontativ und direkt","diplomatisch","leidenschaftlich","sarkastisch","pragmatisch","stur","neugierig","charismatisch","pedantisch","spontan","kompromissbereit"]
DEFAULT_LAW = "Der Bund soll ein Gesetz beschließen, das öffentliche Gebäude verpflichtet, ihren Energieverbrauch innerhalb der nächsten fünf Jahre deutlich zu senken."


def similarity(a, b):
    return 1 - sum(abs(a[x] - b[x]) / 200 for x in AXES) / len(AXES)


def clamp(v, lo=-100, hi=100):
    return max(lo, min(hi, v))


def signed_axis(value):
    return value / 100.0


def axis_agreement(a, b):
    """1.0 = identical, 0.0 = opposite ends of an axis."""
    return 1.0 - abs(a - b) / 200.0


def clamp_pct(v):
    return max(0, min(100, v))


class Member:
    def __init__(self, number, party, rng):
        self.number = number
        self.party = party
        self.name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        self.personality = rng.choice(PERSONALITIES)
        base = PARTIES[party]["values"]
        # Every MP must stay within 68 points of the party on EVERY axis: at least 66%
        # agreement when the full -100..+100 axis is treated as the reference range.
        self.values = {
            axis: int(clamp(base[axis] + rng.randint(-68, 68)))
            for axis in AXES
        }
        self.party_loyalty = rng.randint(35, 90)
        self.party_relation = rng.randint(40, 90)
        self.relationships = {}
        self.speeches = 0
        self.interventions = 0
        self.persuasion = 0.0
        self.debate_stance = 0.0
        self.vote = None
        self.last_reason = ""
        self.last_vote_score = 0.0

    def relation(self, other):
        return self.relationships.get(other, 0)

    def change_relation(self, other, delta):
        self.relationships[other] = clamp(self.relation(other) + delta, -100, 100)


class Simulation:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.members = []
        self.running = False
        self.current_speaker = None
        self.law = DEFAULT_LAW
        self.phase = "BEREIT"
        self.round = 0
        self.max_rounds = 7
        self.amendment = None
        self.amendment_author = None
        self.amendment_passed = False
        self.amendment_votes = {"Ja": 0, "Nein": 0, "Enthalten": 0}
        self.final_votes = {"Ja": 0, "Nein": 0, "Enthalten": 0}
        self.last_vote_reasons = []
        self.law_profile_cache = None
        self._make_members()

    def _make_members(self):
        n = 1
        for party, cfg in PARTIES.items():
            for _ in range(cfg["seats"]):
                self.members.append(Member(n, party, self.rng))
                n += 1
        for m in self.members:
            pool = [x for x in self.members if x.number != m.number]
            for other in self.rng.sample(pool, 4):
                m.change_relation(other.number, self.rng.randint(-28, 28))

    def get(self, number):
        return next(m for m in self.members if m.number == number)

    def next_speaker(self):
        pool = [m for m in self.members if m.number != self.current_speaker]
        weights = []
        for m in pool:
            novelty = 1.45 if m.speeches == 0 else 0.35
            conflict = 0.65 if m.personality in ("konfrontativ und direkt", "leidenschaftlich", "spontan", "sarkastisch") else 0.28
            stance = 0.15 + abs(m.debate_stance) / 30
            weights.append(max(0.1, novelty + conflict * self.rng.random() + stance * self.rng.random()))
        return self.rng.choices(pool, weights=weights, k=1)[0]

    def reactees(self, speaker):
        pool = [m for m in self.members if m.number != speaker.number]
        pool.sort(key=lambda m: (abs(similarity(m.values, speaker.values) - .5), -abs(m.relation(speaker.number))))
        return self.rng.sample(pool[:20], min(6, len(pool[:20])))

    def law_profile(self, law=None):
        text = (law or self.law).lower()
        p = {axis: 0 for axis in AXES}

        # Directional heuristic: unlike the old model, the same topic can push a value
        # either way depending on the wording. This produces a centered voting signal.
        rules = [
            ("oekologie", ["klima", "emission", "co2", "erneuerbar", "umwelt", "nachhalt", "energieeffizienz"], +28),
            ("oekologie", ["kohlekraft", "fossil", "ölbohr", "dieselprivileg"], -26),
            ("sozialstaat", ["sozial", "rente", "kindergeld", "miete", "armut", "pflege", "gesundheit", "bürgergeld", "förderung"], +28),
            ("sozialstaat", ["kürzen", "streichen", "leistungskürzung"], -28),
            ("staat_markt", ["verpflichtet", "verbot", "regulierung", "staatlich", "öffentlich", "kontrolle", "pflicht"], -28),
            ("staat_markt", ["privatis", "markt", "deregulier", "freiwillig", "unternehmerisch"], +28),
            ("international", ["eu", "europa", "international", "ausland", "grenzüberschreit", "aufnahme"], +28),
            ("international", ["grenzkontrolle", "national", "souveränität", "ausstieg", "abschiebung"], -28),
            ("liberalitaet", ["freiheit", "selbstbestimmung", "privat", "datenschutz", "wahlfreiheit"], +28),
            ("liberalitaet", ["überwachung", "kontrolle", "verpflichtende daten", "zugriff auf daten"], -30),
            ("wirtschaftswachstum", ["wirtschaft", "unternehmen", "industrie", "investition", "wachstum", "arbeitsplatz", "entlastung", "steuersenkung"], +27),
            ("wirtschaftswachstum", ["steuererhöhung", "zusatzkosten", "belastung der unternehmen", "einschränkung der industrie"], -27),
            ("progressivitaet", ["reform", "modern", "digital", "gleichstellung", "fortschritt", "neuregelung"], +27),
            ("progressivitaet", ["tradition", "bewahren", "rückkehr", "wiederherstellen", "konservieren"], -25),
        ]
        for axis, words, delta in rules:
            hits = sum(text.count(word) for word in words)
            if hits:
                p[axis] = clamp(p[axis] + min(68, hits * 22 if delta > 0 else hits * 20) * (1 if delta > 0 else -1))

        if any(w in text for w in ["senken", "reduzieren", "verpflichtet", "verbot"]):
            p["staat_markt"] = clamp(p["staat_markt"] - 16)
        if any(w in text for w in ["fördern", "investieren", "ausbauen"]):
            p["wirtschaftswachstum"] = clamp(p["wirtschaftswachstum"] + 16)
        return p

    def law_alignment(self, member, law=None):
        profile = self.law_profile(law)
        return similarity(member.values, profile)

    def policy_score(self, member, law=None):
        """Centered policy compatibility in roughly -1..+1.
        Positive means the member's own value direction supports the law's direction.
        Neutral laws (50 on an axis) contribute nothing.
        """
        profile = self.law_profile(law)
        contributions = []
        for axis in AXES:
            law_dir = signed_axis(profile[axis])
            member_dir = signed_axis(member.values[axis])
            if abs(law_dir) < 0.08:
                continue
            contributions.append(member_dir * law_dir)
        if not contributions:
            return 0.0
        return sum(contributions) / len(contributions)

    def apply_speech_effects(self, speaker):
        for m in self.reactees(speaker):
            align = similarity(m.values, speaker.values)
            conflict = 1 - align
            delta = self.rng.randint(2, 6) if align > .72 else (-self.rng.randint(2, 7) if align < .32 else self.rng.randint(-2, 2))
            if m.party == speaker.party:
                delta += 1
            if m.relation(speaker.number) < -45:
                delta -= self.rng.randint(1, 3)
            m.change_relation(speaker.number, delta)
            persuasion = (0.50 - conflict) * self.rng.uniform(2.0, 5.5)
            if m.party == speaker.party:
                persuasion *= 0.75
            m.persuasion = clamp(m.persuasion + persuasion, -35, 35)
            m.debate_stance = clamp(m.debate_stance + persuasion * 0.55, -25, 25)
        speaker.speeches += 1
        speaker.party_relation = int(clamp_pct(speaker.party_relation + self.rng.randint(-4, 3)))
        speaker.party_loyalty = int(clamp_pct(speaker.party_loyalty + self.rng.randint(-3, 2)))
        return self.maybe_switch_party(speaker)

    def interruption_candidate(self, speaker):
        candidates = []
        for m in self.members:
            if m.number == speaker.number:
                continue
            disagreement = 1.0 - similarity(m.values, speaker.values)
            tension = max(0.0, -m.relation(speaker.number) / 100)
            debate_opposition = max(0.0, -m.debate_stance / 25)
            party_conflict = 0.20 if m.party != speaker.party else 0.0
            score = disagreement * 0.50 + tension * 0.32 + debate_opposition * 0.12 + party_conflict * 0.06
            candidates.append((m, score))
        candidates.sort(key=lambda x: x[1], reverse=True)
        if not candidates or candidates[0][1] < 0.35:
            return None, 0.0
        top = candidates[:10]
        selected = self.rng.choices([m for m, _ in top], weights=[0.20 + score * 1.4 for _, score in top], k=1)[0]
        score = next(s for m, s in top if m.number == selected.number)
        return selected, score

    def interruption_probability(self, speaker):
        candidate, score = self.interruption_candidate(speaker)
        if not candidate:
            return None, 0.0
        # A speech can simply pass without an interruption. Conflict makes it more likely,
        # but there is never a fixed "one interruption per speech" rule.
        probability = clamp(0.03 + (score - 0.35) * 0.95, 0.0, 0.72)
        return candidate, probability

    def propose_amendment(self):
        """Create a contextual, law-linked amendment. LLM is preferred; fallback is structured."""
        text = self.law.lower()
        candidates = []
        if any(w in text for w in ["verpflicht", "pflicht", "müssen"]):
            candidates += [
                "die Verpflichtung auf öffentliche Gebäude ab 500 m² Nutzfläche zu begrenzen",
                "eine Härtefallausnahme für Gebäude mit nachgewiesenen technischen Einschränkungen einzuführen",
                "die Umsetzung zunächst auf besonders energieintensive Gebäude zu konzentrieren",
            ]
        if any(w in text for w in ["fördern", "förderung", "zuschuss", "finanz"]):
            candidates += [
                "die Förderung auf einen festen Höchstbetrag pro Antrag zu begrenzen",
                "die Förderung an einen jährlichen Evaluationsbericht zu knüpfen",
                "kleine Einrichtungen mit geringem Budget zusätzlich zu berücksichtigen",
            ]
        if any(w in text for w in ["steuer", "abgabe", "beitrag"]):
            candidates += [
                "eine Übergangsregelung für die ersten zwei Jahre vorzusehen",
                "eine soziale Ausnahmeregelung für besonders belastete Haushalte einzuführen",
                "die Regelung nach zwei Jahren anhand ihrer tatsächlichen Wirkung zu überprüfen",
            ]
        if any(w in text for w in ["verbot", "untersagt"]):
            candidates += [
                "eine eng definierte Ausnahme für nachweislich unvermeidbare Fälle vorzusehen",
                "das Verbot erst nach einer Übergangsphase vollständig wirksam werden zu lassen",
            ]
        if any(w in text for w in ["digital", "daten", "plattform", "software"]):
            candidates += [
                "eine unabhängige Prüfung des Datenschutzes vor der vollständigen Umsetzung vorzuschreiben",
                "eine regelmäßige Sicherheitsüberprüfung der technischen Infrastruktur vorzusehen",
            ]
        if not candidates:
            candidates = [
                "die Regelung nach zwei Jahren anhand ihrer tatsächlichen Wirkung zu überprüfen",
                "eine klar definierte Härtefallregelung für besondere Einzelfälle einzuführen",
                "die Umsetzung schrittweise zu gestalten und nach dem ersten Jahr zu evaluieren",
            ]
        return self.rng.choice(candidates)

    def vote_choice(self, member, law=None, amendment=False):
        policy = self.policy_score(member, law)
        debate = clamp(member.debate_stance / 25, -1, 1)
        persuasion = clamp(member.persuasion / 35, -1, 1)

        # Party pressure is directional: loyalty pushes toward the party's own policy fit,
        # but cannot erase a strong personal position.
        party_values = PARTIES[member.party]["values"]
        party_policy = self._party_policy_score(member, party_values, law)
        loyalty = (member.party_loyalty - 50) / 50
        party_pressure = party_policy * loyalty * 0.32

        personal = policy * 1.55 + debate * 0.30 + persuasion * 0.18 + party_pressure * 0.42
        personality_bias = {
            "stur": 0.08, "konfrontativ und direkt": -0.03, "diplomatisch": 0.02,
            "kompromissbereit": 0.08, "leidenschaftlich": 0.02, "sarkastisch": -0.01,
        }.get(member.personality, 0.0)
        score = personal + personality_bias + self.rng.uniform(-0.08, 0.08)
        if amendment:
            score *= 0.92
            score += self.rng.uniform(-0.10, 0.10)

        # Wider middle band = meaningful abstentions; yes/no require a real preference.
        if score >= 0.18:
            choice = "Ja"
        elif score <= -0.18:
            choice = "Nein"
        else:
            choice = "Enthalten"
        member.last_vote_score = score
        member.last_reason = f"Politik {policy:+.2f} · Debatte {debate:+.2f} · Partei {party_pressure:+.2f}"
        return choice

    def _party_policy_score(self, member, values, law):
        profile = self.law_profile(law)
        contributions = []
        for axis in AXES:
            law_dir = signed_axis(profile[axis])
            party_dir = signed_axis(values[axis])
            if abs(law_dir) >= 0.08:
                contributions.append(party_dir * law_dir)
        return sum(contributions) / len(contributions) if contributions else 0.0

    def perform_vote(self, law=None, amendment=False):
        counts = {"Ja": 0, "Nein": 0, "Enthalten": 0}
        for m in self.members:
            choice = self.vote_choice(m, law, amendment)
            if not amendment:
                m.vote = choice
            counts[choice] += 1
        if amendment:
            self.amendment_votes = counts
        else:
            self.final_votes = counts
        return counts

    def update_after_vote(self):
        events = []
        for m in self.members:
            if m.vote == "Ja":
                m.party_relation = int(clamp_pct(m.party_relation + self.rng.randint(-1, 3)))
                m.party_loyalty = int(clamp_pct(m.party_loyalty + self.rng.randint(-1, 2)))
            elif m.vote == "Nein":
                m.party_relation = int(clamp_pct(m.party_relation + self.rng.randint(-4, 1)))
                m.party_loyalty = int(clamp_pct(m.party_loyalty + self.rng.randint(-3, 2)))
            else:
                m.party_relation = int(clamp_pct(m.party_relation + self.rng.randint(-2, 2)))
            event = self.maybe_switch_party(m)
            if event:
                events.append(event)
        return events

    def maybe_switch_party(self, m):
        if m.party_loyalty >= 18 or m.party_relation >= 18:
            return None
        alternatives = [(p, similarity(m.values, PARTIES[p]["values"])) for p in PARTIES if p != m.party]
        best, score = max(alternatives, key=lambda x: x[1])
        if score <= 0.64:
            return None
        old = m.party
        m.party = best
        m.party_loyalty = 45
        m.party_relation = 55
        return f"#{m.number} {m.name} wechselt von {old} zu {best}."


class Ollama:
    @staticmethod
    def chat(system, prompt, temperature=.9, timeout=90):
        payload = {
            "model": MODEL,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())["message"]["content"].strip()

    @staticmethod
    def speech(member, law, recent_events):
        system = (
            "Du bist ein fiktiver Abgeordneter in einer politischen Simulation. "
            "Keine reale Person imitieren. Schreibe eine eigenständige deutsche Parlamentsrede mit etwa 70 bis 105 Wörtern. "
            "Reagiere konkret auf den Gesetzentwurf und mindestens ein vorheriges Debattenereignis. "
            "Die Figur darf zustimmen, widersprechen, provozieren oder Kompromisse suchen. "
            "Bleibe sachlich genug für eine politische Simulation; keine erfundenen Tatsachen über reale Personen."
        )
        vals = ", ".join(f"{AXIS_LABELS[a]}={member.values[a]}" for a in AXES)
        context = " | ".join(recent_events[-7:]) if recent_events else "Keine vorherigen Ereignisse."
        prompt = (
            f"Gesetzentwurf: {law}\nAbgeordneter: {member.name}\nPartei: {member.party}\n"
            f"Persönlichkeit: {member.personality}\nPolitische Werte: {vals}\n"
            f"Parteitreue: {member.party_loyalty}%\nBeziehung zur Partei: {member.party_relation}%\n"
            f"Eigene Debattenhaltung: {member.debate_stance:+.1f}\nLetzte Ereignisse: {context}\n"
            "Halte jetzt die nächste Rede. Wiederhole nicht einfach den Gesetzentwurf."
        )
        return Ollama.chat(system, prompt, .88)

    @staticmethod
    def interruption(interrupter, speaker, law):
        system = (
            "Du bist ein fiktiver Abgeordneter in einer Parlamentsdebatte. "
            "Schreibe genau einen sehr kurzen, pointierten Zwischenruf auf Deutsch. "
            "Maximal 7 Wörter. Keine Beleidigungen. Kein Vorwort."
        )
        prompt = (
            f"Gesetz: {law}\nSprecher: {speaker.name}, Partei {speaker.party}\n"
            f"Zwischenrufer: {interrupter.name}, Partei {interrupter.party}, Persönlichkeit {interrupter.personality}. "
            "Der Zwischenruf soll konkrete Ablehnung oder persönliche Spannung ausdrücken."
        )
        return Ollama.chat(system, prompt, .96, timeout=35)

    @staticmethod
    def new_law():
        system = (
            "Du erfindest einen fiktiven deutschen Gesetzentwurf für eine politische Simulation. "
            "Er soll konkret, realistisch und in 1 bis 2 Sätzen formuliert sein. "
            "Keine realen Politiker, keine erfundenen aktuellen Ereignisse. "
            "Thema frei wählen: Wirtschaft, Bildung, Energie, Wohnen, Verkehr, Digitales, Soziales, Umwelt oder Verwaltung. "
            "Nur den Gesetzentwurf ausgeben."
        )
        return Ollama.chat(system, "Erstelle den nächsten Gesetzentwurf für AFFENKÄFIG.", .9, timeout=45)

    @staticmethod
    def amendment(law, author, party):
        system = (
            "Du bist ein fiktiver Abgeordneter in einer politischen Simulation. "
            "Formuliere einen einzigen realistischen Änderungsantrag, der sich unmittelbar auf den vorliegenden Gesetzentwurf bezieht. "
            "Er darf keine neue, völlig unabhängige Politik erfinden. Verändere eine konkrete Frist, Schwelle, Ausnahme, Zielgruppe, Finanzierung, Übergangsregelung oder Kontrollmechanik, sofern diese zum Text passt. "
            "Maximal 35 Wörter. Nur den Änderungsantrag ausgeben."
        )
        prompt = f"Gesetzentwurf: {law}\nAntragsteller: {author}, Partei {party}\nFormuliere den Änderungsantrag."
        return Ollama.chat(system, prompt, .72, timeout=40)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1560x960")
        self.minsize(1180, 760)
        self.configure(bg="#0e1014")
        self.sim = Simulation()
        self.paused = False
        self.speech_token = 0
        self.generation_token = 0
        self.interruption_token = 0
        self.vote_token = 0
        self.recent_events = []
        self.bubble_after = None
        self.current_words = []
        self.current_speech_member = None
        self.speech_active = False
        self.transition_after = None
        self.speed = tk.DoubleVar(value=1.0)
        self.infinite_mode = tk.BooleanVar(value=False)
        self.selected_member = None
        self.selected_party = None
        self.configure_styles()
        self.build()
        self.draw_seats()
        self.show_profile(self.sim.members[0])
        self.update_party_counts()

    def configure_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TButton", font=("Segoe UI Semibold", 9), padding=(12, 8), background="#232831", foreground="#eef1f5", borderwidth=0)
        s.map("TButton", background=[("active", "#343b46"), ("disabled", "#1b1e24")], foreground=[("disabled", "#656b75")])
        s.configure("Accent.TButton", background="#e5e8ed", foreground="#111318")
        s.map("Accent.TButton", background=[("active", "#ffffff")])
        s.configure("TScale", background="#171a20", troughcolor="#2b3039")

    def panel(self, parent, bg="#171a20"):
        return tk.Frame(parent, bg=bg, highlightthickness=1, highlightbackground="#272c34")

    def build(self):
        # Header
        top = tk.Frame(self, bg="#0e1014")
        top.pack(fill="x", padx=22, pady=(18, 10))
        brand = tk.Frame(top, bg="#0e1014"); brand.pack(side="left")
        tk.Label(brand, text="AFFENKÄFIG", bg="#0e1014", fg="#f4f6f8", font=("Segoe UI Semibold", 27)).pack(anchor="w")
        tk.Label(brand, text="63 FIKTIVE ABGEORDNETE · POLITISCHE SIMULATION", bg="#0e1014", fg="#707784", font=("Segoe UI", 9)).pack(anchor="w")

        self.phase_label = tk.Label(top, text="BEREIT", bg="#0e1014", fg="#aeb4be", font=("Segoe UI Semibold", 10))
        self.phase_label.pack(side="left", padx=28, pady=(12,0))
        controls = tk.Frame(top, bg="#0e1014"); controls.pack(side="right")
        self.start_btn = ttk.Button(controls, text="▶ Sitzung", command=self.start, style="Accent.TButton"); self.start_btn.pack(side="left", padx=3)
        self.next_btn = ttk.Button(controls, text="⏭ Weiter", command=self.next_step); self.next_btn.pack(side="left", padx=3)
        self.pause_btn = ttk.Button(controls, text="⏸ Pause", command=self.pause); self.pause_btn.pack(side="left", padx=3)
        ttk.Checkbutton(controls, text="∞ Unendlich", variable=self.infinite_mode, command=self.update_infinite_label).pack(side="left", padx=(8,3))
        ttk.Button(controls, text="↻ Neue Welt", command=self.new_sim).pack(side="left", padx=3)

        # Law card
        law = self.panel(self)
        law.pack(fill="x", padx=22, pady=(0, 9))
        law_head = tk.Frame(law, bg="#171a20"); law_head.pack(fill="x", padx=14, pady=(9, 3))
        tk.Label(law_head, text="GESETZENTWURF", bg="#171a20", fg="#7e8590", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.law_meta = tk.Label(law_head, text="Bereit für die erste Sitzung", bg="#171a20", fg="#606772", font=("Segoe UI", 8)); self.law_meta.pack(side="right")
        self.law_var = tk.StringVar(value=DEFAULT_LAW)
        self.law_entry = tk.Entry(law, textvariable=self.law_var, bg="#171a20", fg="#eef1f5", insertbackground="#eef1f5", relief="flat", font=("Segoe UI", 12))
        self.law_entry.pack(fill="x", padx=14, pady=(0, 10))

        # Party strip
        self.party_strip = tk.Frame(self, bg="#0e1014")
        self.party_strip.pack(fill="x", padx=22, pady=(0, 9))
        self.party_cards = {}
        for party, cfg in PARTIES.items():
            card = tk.Frame(self.party_strip, bg="#15181e", highlightthickness=1, highlightbackground="#242933")
            card.pack(side="left", fill="x", expand=True, padx=3)
            dot = tk.Frame(card, bg=cfg["color"], width=6); dot.pack(side="left", fill="y")
            body = tk.Frame(card, bg="#15181e"); body.pack(side="left", fill="both", expand=True, padx=8, pady=6)
            name = tk.Label(body, text=party, bg="#15181e", fg="#e8ebef", font=("Segoe UI Semibold", 8), anchor="w", cursor="hand2"); name.pack(fill="x")
            count = tk.Label(body, text=f"{cfg['seats']} Sitze", bg="#15181e", fg="#727984", font=("Segoe UI", 8), anchor="w", cursor="hand2"); count.pack(fill="x")
            for widget in (card, dot, body, name, count):
                widget.bind("<Button-1>", lambda e, p=party: self.show_party(p))
            self.party_cards[party] = count

        body = tk.Frame(self, bg="#0e1014")
        body.pack(fill="both", expand=True, padx=22, pady=(0, 18))

        # Main column
        main = tk.Frame(body, bg="#0e1014")
        main.pack(side="left", fill="both", expand=True, padx=(0, 10))
        plenary = self.panel(main)
        plenary.pack(fill="both", expand=True)
        head = tk.Frame(plenary, bg="#171a20"); head.pack(fill="x", padx=14, pady=(11, 3))
        tk.Label(head, text="PLENARSAAL", bg="#171a20", fg="#858c97", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.seat_hint = tk.Label(head, text="Sitz anklicken → Profil", bg="#171a20", fg="#5f6671", font=("Segoe UI", 8)); self.seat_hint.pack(side="right")
        self.canvas = tk.Canvas(plenary, bg="#171a20", highlightthickness=0, height=430)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.canvas.bind("<Button-1>", self.click_seat)

        speaker_box = tk.Frame(plenary, bg="#1d2229", highlightthickness=1, highlightbackground="#2b313b")
        speaker_box.pack(fill="x", padx=12, pady=(4, 12))
        speaker_top = tk.Frame(speaker_box, bg="#1d2229"); speaker_top.pack(fill="x", padx=14, pady=(10, 0))
        self.speaker = tk.Label(speaker_top, text="Noch keine Rede", bg="#1d2229", fg="#f2f4f7", font=("Segoe UI Semibold", 14), anchor="w"); self.speaker.pack(side="left")
        self.status = tk.Label(speaker_top, text="Bereit", bg="#1d2229", fg="#777f8b", font=("Segoe UI", 9)); self.status.pack(side="right")
        self.speech = tk.Text(speaker_box, height=7, wrap="word", bg="#1d2229", fg="#e9edf2", relief="flat", font=("Georgia", 12), padx=14, pady=8)
        self.speech.pack(fill="x", padx=4, pady=(3, 6)); self.speech.config(state="disabled")
        speed_row = tk.Frame(speaker_box, bg="#1d2229"); speed_row.pack(fill="x", padx=14, pady=(0, 9))
        tk.Label(speed_row, text="Rede-Tempo", bg="#1d2229", fg="#6e7682", font=("Segoe UI", 8)).pack(side="left")
        ttk.Scale(speed_row, from_=0.65, to=2.0, variable=self.speed, orient="horizontal", length=130).pack(side="left", padx=8)
        self.speed_value = tk.Label(speed_row, text="1.0×", bg="#1d2229", fg="#b5bbc4", font=("Segoe UI Semibold", 8)); self.speed_value.pack(side="left")
        self.speed.trace_add("write", self.update_speed_label)
        ttk.Button(speed_row, text="⏩ Rede überspringen", command=self.skip_speech).pack(side="right")

        # Right rail
        rail = tk.Frame(body, bg="#0e1014", width=390)
        rail.pack(side="left", fill="y"); rail.pack_propagate(False)

        live_panel = self.panel(rail); live_panel.pack(fill="both", expand=True, pady=(0, 10))
        lh = tk.Frame(live_panel, bg="#171a20"); lh.pack(fill="x", padx=12, pady=(11, 5))
        tk.Label(lh, text="LIVE / DEBATTE", bg="#171a20", fg="#858c97", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.round_label = tk.Label(lh, text="0 / 7", bg="#171a20", fg="#626a76", font=("Segoe UI Semibold", 9)); self.round_label.pack(side="right")
        self.live = tk.Text(live_panel, bg="#171a20", fg="#cfd4dc", relief="flat", font=("Consolas", 9), wrap="word")
        self.live.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.live.config(state="disabled")

        profile_panel = self.panel(rail); profile_panel.pack(fill="both", expand=True)
        ph = tk.Frame(profile_panel, bg="#171a20"); ph.pack(fill="x", padx=12, pady=(11, 5))
        tk.Label(ph, text="ABGEORDNETER", bg="#171a20", fg="#858c97", font=("Segoe UI Semibold", 9)).pack(side="left")
        self.profile_tag = tk.Label(ph, text="#—", bg="#171a20", fg="#636b76", font=("Segoe UI Semibold", 9)); self.profile_tag.pack(side="right")
        self.profile_body = tk.Frame(profile_panel, bg="#171a20")
        self.profile_body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def update_speed_label(self, *_):
        self.speed_value.config(text=f"{self.speed.get():.1f}×")

    def update_party_counts(self):
        counts = {p: 0 for p in PARTIES}
        for m in self.sim.members:
            counts[m.party] = counts.get(m.party, 0) + 1
        for p, label in self.party_cards.items():
            label.config(text=f"{counts.get(p, 0)} Sitze")

    def set_speech(self, text):
        self.speech.config(state="normal"); self.speech.delete("1.0", "end"); self.speech.insert("1.0", text); self.speech.config(state="disabled")

    def log(self, text):
        self.recent_events.append(text)
        self.recent_events = self.recent_events[-30:]
        self.live.config(state="normal")
        self.live.insert("end", text + "\n")
        self.live.see("end")
        self.live.config(state="disabled")

    def seat_position(self, number):
        """Single source of truth for seat coordinates."""
        w = max(self.canvas.winfo_width(), 720)
        h = max(self.canvas.winfo_height(), 430)
        cx, cy = w / 2, h * 0.43
        rx, ry = w * 0.40, h * 0.34
        i = number - 1
        row, pos = divmod(i, 15)
        angle = math.radians(198 + pos * (144 / 14))
        return cx + (rx - row * 34) * math.cos(angle), cy + (ry - row * 26) * math.sin(angle)

    def draw_seats(self, active=None, vote_map=False):
        c = self.canvas
        c.delete("all")
        w = max(c.winfo_width(), 720)
        h = max(c.winfo_height(), 430)
        cx = w / 2
        floor_y = h * 0.72

        # Plenary floor / lectern are deliberately BELOW the member rows.
        c.create_arc(w*.18, h*.06, w*.82, h*.82, start=198, extent=144,
                     style="arc", outline="#252b33", width=2)

        for m in self.sim.members:
            # While speaking, the MP leaves the seat and is shown at the lectern.
            if self.current_speech_member == m.number and self.speech_active:
                continue

            x, y = self.seat_position(m.number)
            r = 10
            fill = PARTIES[m.party]["color"]
            outline = "#303641"
            width = 1

            if self.selected_member == m.number:
                outline = "#f3f5f8"
                width = 2

            if self.selected_member is not None and self.selected_member != m.number:
                selected = self.sim.get(self.selected_member)
                rel = selected.relation(m.number)
                if rel >= 25:
                    outline = "#54c878"
                    width = 3
                elif rel <= -25:
                    outline = "#e05b5b"
                    width = 3

            if vote_map and m.vote:
                outline = {"Ja": "#f3f5f8", "Nein": "#e05b5b", "Enthalten": "#9da5b0"}[m.vote]
                width = 3

            c.create_oval(x-r, y-r, x+r, y+r, fill=fill, outline=outline,
                          width=width, tags=(f"seat_{m.number}", "seat"))
            c.create_text(x, y, text=str(m.number), fill="#ffffff",
                          font=("Segoe UI Semibold", 7), tags=(f"seat_{m.number}", "seat"))

        # A clearly separated speaker area below the parliament.
        c.create_rectangle(w*.27, floor_y, w*.73, floor_y+3, fill="#2a3038", outline="")
        c.create_rectangle(cx-110, floor_y+16, cx+110, floor_y+52,
                           fill="#252b33", outline="#39414b", width=1)
        c.create_rectangle(cx-78, floor_y+7, cx+78, floor_y+25,
                           fill="#303740", outline="#424b56")

        if self.current_speech_member and self.speech_active:
            m = self.sim.get(self.current_speech_member)
            # Speaker standing immediately behind the lectern.
            c.create_oval(cx-17, floor_y-55, cx+17, floor_y-21,
                          fill=PARTIES[m.party]["color"], outline="#f3f5f8", width=2)
            c.create_text(cx, floor_y-38, text=str(m.number), fill="#fff",
                          font=("Segoe UI Semibold", 8))
            c.create_text(cx, floor_y+68, text=f"REDNERPULT · #{m.number} {m.name}",
                          fill="#dce1e7", font=("Segoe UI Semibold", 9))
        else:
            c.create_text(cx, floor_y+68, text="REDNERPULT",
                          fill="#6f7782", font=("Segoe UI Semibold", 9))

        if vote_map:
            c.create_text(16, h-15, anchor="w", text="JA", fill="#f3f5f8", font=("Segoe UI", 8))
            c.create_text(55, h-15, anchor="w", text="NEIN", fill="#e05b5b", font=("Segoe UI", 8))
            c.create_text(112, h-15, anchor="w", text="ENTHALTEN", fill="#9da5b0", font=("Segoe UI", 8))
        elif self.selected_member is not None:
            c.create_text(16, h-15, anchor="w",
                          text="GRÜN = positive Beziehung · ROT = negative Beziehung · Klick = Profil",
                          fill="#7d8490", font=("Segoe UI", 8))

    def click_seat(self, event):
        best = None; dist = 999
        for m in self.sim.members:
            x, y = self.seat_position(m.number)
            d = (x-event.x)**2 + (y-event.y)**2
            if d < dist:
                dist = d; best = m
        if best and dist < 30**2:
            self.selected_member = best.number
            self.show_profile(best)
            self.draw_seats(self.sim.current_speaker)

    def clear_profile(self):
        for child in self.profile_body.winfo_children():
            child.destroy()

    def value_bar(self, parent, label, value, color="#8f98a6"):
        row = tk.Frame(parent, bg="#171a20"); row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg="#171a20", fg="#cbd0d7", font=("Segoe UI", 8), width=18, anchor="w").pack(side="left")
        bar = tk.Canvas(row, bg="#171a20", height=18, width=170, highlightthickness=0); bar.pack(side="left", padx=4)
        x0, x1, mid = 3, 167, 85
        bar.create_rectangle(x0, 6, x1, 12, fill="#2a3038", outline="")
        bar.create_line(mid, 3, mid, 15, fill="#5c6470", width=1)
        px = mid + (value / 100.0) * 78
        bar.create_rectangle(min(mid, px), 6, max(mid, px), 12, fill=color, outline="")
        tk.Label(row, text=f"{value:+d}", bg="#171a20", fg="#eef1f5", font=("Segoe UI Semibold", 8), width=5, anchor="e").pack(side="left")
        tk.Label(row, text="−100", bg="#171a20", fg="#5f6671", font=("Segoe UI", 6)).place(in_=bar, x=0, y=0)
        tk.Label(row, text="+100", bg="#171a20", fg="#5f6671", font=("Segoe UI", 6)).place(in_=bar, x=137, y=0)

    def show_profile(self, m):
        self.selected_member = m.number; self.selected_party = None
        self.profile_tag.config(text=f"#{m.number}", fg=PARTIES[m.party]["color"])
        self.clear_profile()
        tk.Label(self.profile_body, text=m.name, bg="#171a20", fg="#f1f3f6", font=("Segoe UI Semibold", 15), anchor="w").pack(fill="x")
        tk.Label(self.profile_body, text=f"{m.party}  ·  {m.personality}", bg="#171a20", fg="#8f97a3", font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(1,8))
        stat = tk.Frame(self.profile_body, bg="#171a20"); stat.pack(fill="x", pady=(0,8))
        for text in (f"Treue {m.party_loyalty}%", f"Partei {m.party_relation}%", f"Reden {m.speeches}", f"Zwischenrufe {m.interventions}"):
            tk.Label(stat, text=text, bg="#22272f", fg="#d5dae0", font=("Segoe UI Semibold", 7), padx=7, pady=5).pack(side="left", padx=(0,4))
        tk.Label(self.profile_body, text="POLITISCHE WERTE", bg="#171a20", fg="#7f8792", font=("Segoe UI Semibold", 8), anchor="w").pack(fill="x", pady=(3,2))
        bars = tk.Frame(self.profile_body, bg="#171a20"); bars.pack(fill="x")
        for axis in AXES:
            self.value_bar(bars, AXIS_LABELS[axis], m.values[axis], PARTIES[m.party]["color"])
        if m.vote:
            tk.Label(self.profile_body, text=f"LETZTE ABSTIMMUNG  ·  {m.vote}  ·  {m.last_vote_score:+.2f}", bg="#171a20", fg="#e5e9ee", font=("Segoe UI Semibold", 8), anchor="w").pack(fill="x", pady=(10,2))
            tk.Label(self.profile_body, text=m.last_reason, bg="#171a20", fg="#7d8590", font=("Segoe UI", 7), anchor="w", wraplength=330, justify="left").pack(fill="x")
        self.draw_seats()

    def show_party(self, party):
        self.selected_party = party; self.selected_member = None
        cfg = PARTIES[party]
        self.profile_tag.config(text="PARTEI", fg=cfg["color"])
        self.clear_profile()
        tk.Label(self.profile_body, text=party, bg="#171a20", fg="#f1f3f6", font=("Segoe UI Semibold", 15), anchor="w").pack(fill="x")
        count = sum(m.party == party for m in self.sim.members)
        tk.Label(self.profile_body, text=f"{count} Sitze · Simulationsprofil", bg="#171a20", fg="#8f97a3", font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(1,10))
        tk.Label(self.profile_body, text="PARTEIWERTE", bg="#171a20", fg="#7f8792", font=("Segoe UI Semibold", 8), anchor="w").pack(fill="x", pady=(3,2))
        bars = tk.Frame(self.profile_body, bg="#171a20"); bars.pack(fill="x")
        for axis in AXES:
            self.value_bar(bars, AXIS_LABELS[axis], cfg["values"][axis], cfg["color"])
        tk.Label(self.profile_body, text="Alle Werte sind Simulationsparameter auf einer Skala von −100 bis +100.", bg="#171a20", fg="#656d78", font=("Segoe UI", 7), wraplength=340, justify="left").pack(fill="x", pady=(10,0))
        self.draw_seats()

    def generate(self, m):
        try:
            return Ollama.speech(m, self.sim.law, self.recent_events)
        except Exception:
            return self.fallback_speech(m)

    def fallback_speech(self, m):
        stance = self.sim.policy_score(m, self.sim.law)
        if stance > .28:
            return f"Dieser Gesetzentwurf geht in die richtige Richtung. Wir sollten handeln, statt Probleme weiter zu vertagen. Entscheidend ist aber, dass die Umsetzung nachvollziehbar bleibt und nicht an der Realität vorbeigeht. Ich unterstütze das Ziel, möchte aber klare Kriterien, damit am Ende nicht nur gute Absichten beschlossen werden."
        if stance < -.28:
            return f"Ich halte diesen Entwurf in seiner jetzigen Form für den falschen Weg. Er greift tief in bestehende Abläufe ein, ohne überzeugend zu zeigen, dass der Nutzen die Folgen rechtfertigt. Wir sollten die Maßnahme grundlegend überarbeiten, statt heute einen Beschluss zu fassen, den wir später korrigieren müssen."
        return f"Ich sehe in diesem Entwurf nachvollziehbare Ziele, aber auch offene Fragen. Für mich entscheidet sich die Zustimmung daran, wie konkret die Umsetzung ausgestaltet wird. Wenn wir die problematischen Punkte korrigieren und die Wirkung überprüfbar machen, ist ein Kompromiss möglich. In der jetzigen Form bleiben mir jedoch zu viele Punkte offen."

    def animate(self, m, text):
        self.speech_token += 1
        token = self.speech_token
        self.speech_active = True
        self.current_speech_member = m
        if self.transition_after:
            try:
                self.after_cancel(self.transition_after)
            except Exception:
                pass
            self.transition_after = None
        words = " ".join(text.replace("\n", " ").split()).split()
        self.current_words = words
        self.set_speech("")
        self.speaker.config(text=f"#{m.number}  {m.name}  ·  {m.party}")
        self.status.config(text="spricht …")
        self.draw_seats(m.number)
        self.schedule_interruption(m, token, len(words))
        base = 30000 / max(1, len(words))
        interval = int(clamp(base / max(.65, self.speed.get()), 35, 180))
        self.reveal(words, 0, interval, token, m)

    def schedule_interruption(self, speaker, speech_token, word_count):
        self.interruption_token += 1
        token = self.interruption_token
        interrupter, probability = self.sim.interruption_probability(speaker)
        if not interrupter or self.sim.rng.random() > probability or word_count < 28:
            return
        delay = self.sim.rng.randint(3800, min(14500, max(6200, word_count * 115)))
        def trigger():
            if token != self.interruption_token or speech_token != self.speech_token or self.paused or not self.sim.running:
                return
            live, live_probability = self.sim.interruption_probability(speaker)
            if not live or self.sim.rng.random() > min(0.92, live_probability + .12):
                return
            interrupter = live
            interrupter.interventions += 1
            try:
                text = Ollama.interruption(interrupter, speaker, self.sim.law)
            except Exception:
                text = self.fallback_interruption(interrupter, speaker)
            text = self.short_interruption(text)
            self.show_interruption_bubble(interrupter, text)
            self.log(f"↯ #{interrupter.number} {interrupter.name}: „{text}“")
            self.sim.last_interruption = (interrupter.number, speaker.number, text)
            delta = self.sim.rng.randint(4, 9)
            interrupter.change_relation(speaker.number, -delta)
            speaker.change_relation(interrupter.number, -delta)
            interrupter.debate_stance = clamp(interrupter.debate_stance - self.sim.rng.uniform(0.5, 2.5), -25, 25)
            speaker.debate_stance = clamp(speaker.debate_stance + self.sim.rng.uniform(-1.2, 1.2), -25, 25)
            self.show_profile(interrupter)
        self.after(delay, trigger)

    def short_interruption(self, text):
        text = " ".join(text.replace("\n", " ").split())
        text = text.strip(' .,!?:;"“”')
        words = text.split()[:7]
        text = " ".join(words)
        return (text + "!") if text and text[-1] not in "!?" else text

    def show_interruption_bubble(self, member, text):
        c = self.canvas; c.delete("interruption_bubble")
        x, y = self.seat_position(member.number)
        w = max(150, min(270, len(text) * 7.1 + 26)); h = 44
        bx = max(8, min(c.winfo_width()-w-8, x-w/2)); by = max(18, y-72)
        # Bubble shadow + body + tail.
        c.create_rectangle(bx+2, by+2, bx+w+2, by+h+2, fill="#0b0d11", outline="", tags="interruption_bubble")
        c.create_rectangle(bx, by, bx+w, by+h, fill="#f1f3f6", outline="#cbd1d9", width=1, tags="interruption_bubble")
        c.create_polygon(x-7, by+h, x, by+h+12, x+7, by+h, fill="#f1f3f6", outline="#cbd1d9", tags="interruption_bubble")
        c.create_text(bx+w/2, by+h/2, text=text, fill="#15181d", font=("Segoe UI Semibold", 9), width=w-18, tags="interruption_bubble")
        if self.bubble_after:
            try: self.after_cancel(self.bubble_after)
            except Exception: pass
        self.bubble_after = self.after(3400, lambda: c.delete("interruption_bubble"))

    def fallback_interruption(self, interrupter, speaker):
        options = [
            "Und wer bezahlt das?", "Das überzeugt mich nicht!", "Konkrete Zahlen, bitte!",
            "Das ist völlig unrealistisch!", "Sie ignorieren den Kern!", "So funktioniert das nicht!",
            "Das wird viel zu teuer!", "Genau das ist das Problem!",
        ]
        return self.sim.rng.choice(options)

    def reveal(self, words, i, interval, token, m):
        if token != self.speech_token:
            return
        if self.paused:
            self.after(120, lambda: self.reveal(words, i, interval, token, m)); return
        if i >= len(words):
            self.status.config(text="Rede beendet")
            self.log(f"✓ #{m.number} {m.name} beendet die Rede.")
            event = self.sim.apply_speech_effects(m)
            if event:
                self.log("⚠ " + event)
            self.speech_active = False
            self.current_speech_member = None
            self.show_profile(m)
            self.draw_seats()
            self.transition_after = self.after(650, self._continue_after_speech)
            return
        current = self.speech.get("1.0", "end-1c")
        self.set_speech((current + " " + words[i]).strip())
        self.after(interval, lambda: self.reveal(words, i+1, interval, token, m))

    def _continue_after_speech(self):
        self.transition_after = None
        if self.sim.running and not self.paused and self.sim.phase == "DEBATTE":
            self.next_step()

    def skip_speech(self):
        if not self.sim.running or not self.current_speech_member or self.sim.phase != "DEBATTE":
            return
        self.speech_token += 1
        self.interruption_token += 1
        if self.transition_after:
            try:
                self.after_cancel(self.transition_after)
            except Exception:
                pass
            self.transition_after = None
        m = self.current_speech_member
        self.set_speech(" ".join(self.current_words))
        self.status.config(text="Rede übersprungen")
        self.log(f"⏩ Rede von #{m.number} {m.name} übersprungen.")
        event = self.sim.apply_speech_effects(m)
        if event:
            self.log("⚠ " + event)
        self.speech_active = False
        self.current_speech_member = None
        self.show_profile(m)
        self.draw_seats()
        self.transition_after = self.after(250, self._continue_after_speech)

    def next_step(self):
        if not self.sim.running or self.paused:
            return
        if self.speech_active:
            return
        if self.sim.phase == "DEBATTE":
            if self.sim.round >= self.sim.max_rounds:
                self.begin_amendment(); return
            self.sim.round += 1
            self.round_label.config(text=f"{self.sim.round} / {self.sim.max_rounds}")
            self.phase_label.config(text=f"DEBATTE  {self.sim.round}/{self.sim.max_rounds}")
            self.next_speech()
        elif self.sim.phase == "ÄNDERUNG":
            self.resolve_amendment()
        elif self.sim.phase == "ABSTIMMUNG":
            self.resolve_final_vote()

    def next_speech(self):
        if not self.sim.running or self.paused or self.sim.phase != "DEBATTE":
            return
        self.speech_active = False
        self.current_speech_member = None
        self.interruption_token += 1
        m = self.sim.next_speaker()
        self.sim.current_speaker = m.number
        self.show_profile(m)
        self.draw_seats()
        self.log(f"→ #{m.number} {m.name} ({m.party}) spricht.")
        self.status.config(text="Rede wird erzeugt …")
        self.generation_token += 1
        token = self.generation_token
        threading.Thread(target=self._generate_async, args=(m, token), daemon=True).start()

    def _generate_async(self, m, token):
        text = self.generate(m)
        self.after(0, lambda: self._apply_generated(m, text, token))

    def _apply_generated(self, m, text, token):
        if token != self.generation_token or not self.sim.running or self.sim.phase != "DEBATTE": return
        self.animate(m, text)

    def begin_amendment(self):
        self.sim.phase = "ÄNDERUNG"
        self.phase_label.config(text="ÄNDERUNGSANTRAG")
        self.status.config(text="Änderungsantrag wird formuliert …")
        proposer = self.sim.next_speaker(); self.sim.current_speaker = proposer.number
        try:
            amendment_text = Ollama.amendment(self.sim.law, proposer.name, proposer.party)
            amendment_text = " ".join(amendment_text.replace("\n", " ").split()).strip(' ."“”')
            if not amendment_text or len(amendment_text.split()) > 35:
                raise ValueError("unbrauchbarer Änderungsantrag")
        except Exception:
            amendment_text = self.sim.propose_amendment()
        self.sim.amendment = amendment_text
        self.sim.amendment_author = proposer.number
        self.speaker.config(text=f"Änderungsantrag · #{proposer.number} {proposer.name}")
        self.set_speech(f"ÄNDERUNGSANTRAG\n\n{amendment_text}")
        self.log(f"✎ Änderungsantrag von #{proposer.number} {proposer.name}: {amendment_text}")
        self.after(1200, self.resolve_amendment)

    def resolve_amendment(self):
        if self.paused or not self.sim.running or self.sim.phase != "ÄNDERUNG": return
        self.status.config(text="Änderungsantrag wird abgestimmt …")
        counts = self.sim.perform_vote(self.sim.law + " " + (self.sim.amendment or ""), amendment=True)
        passed = counts["Ja"] > counts["Nein"]
        self.sim.amendment_passed = passed
        self.log(f"✎ Änderungsantrag → JA {counts['Ja']} · NEIN {counts['Nein']} · ENTHALTEN {counts['Enthalten']}")
        if passed:
            self.sim.law += f" [Änderung beschlossen: {self.sim.amendment}.]"
            self.log("✓ Änderungsantrag angenommen.")
        else:
            self.log("✗ Änderungsantrag abgelehnt.")
        self.sim.phase = "ABSTIMMUNG"
        self.phase_label.config(text="ABSTIMMUNG")
        self.status.config(text="Endabstimmung …")
        self.speech_active = False
        self.current_speech_member = None
        self.interruption_token += 1
        self.draw_seats(vote_map=False)
        self.after(1100, self.resolve_final_vote)

    def resolve_final_vote(self):
        if self.paused or not self.sim.running or self.sim.phase != "ABSTIMMUNG": return
        counts = self.sim.perform_vote(self.sim.law, amendment=False)
        self.log("════════ ENDE DER ABSTIMMUNG ════════")
        self.log(f"JA {counts['Ja']} · NEIN {counts['Nein']} · ENTHALTEN {counts['Enthalten']}")
        passed = counts["Ja"] > counts["Nein"]
        self.phase_label.config(text="ANGENOMMEN" if passed else "ABGELEHNT")
        self.status.config(text="Gesetzentwurf angenommen." if passed else "Gesetzentwurf abgelehnt.")
        self.speaker.config(text="Abstimmung beendet")
        self.speech_active = False
        self.current_speech_member = None
        self.set_speech(("ANGENOMMEN" if passed else "ABGELEHNT") + "\n\n" + self.sim.law)
        self.draw_seats(vote_map=True)
        events = self.sim.update_after_vote()
        for event in events: self.log("⚠ " + event)
        self.sim.phase = "ERGEBNIS"
        self.show_vote_summary()
        self.update_party_counts()
        if self.infinite_mode.get():
            self.sim.running = True
            self.status.config(text="Nächster Gesetzentwurf in 10 Sekunden …")
            self.phase_label.config(text="NÄCHSTE SITZUNG")
            self.after(10000, self.start_next_ai_law)
        else:
            self.sim.running = False

    def show_vote_summary(self):
        counts = self.sim.final_votes
        total = max(1, sum(counts.values()))
        self.clear_profile()
        passed = counts["Ja"] > counts["Nein"]
        tk.Label(self.profile_body, text="ABSTIMMUNGSERGEBNIS", bg="#171a20", fg="#f1f3f6", font=("Segoe UI Semibold", 14), anchor="w").pack(fill="x")
        tk.Label(self.profile_body, text=f"{'ANGENOMMEN' if passed else 'ABGELEHNT'} · {total} Stimmen", bg="#171a20", fg="#8f97a3", font=("Segoe UI", 8), anchor="w").pack(fill="x", pady=(1,8))
        for label, key, color in (("JA","Ja","#dce1e7"),("NEIN","Nein","#e05b5b"),("ENTHALTEN","Enthalten","#9da5b0")):
            row=tk.Frame(self.profile_body,bg="#171a20"); row.pack(fill="x",pady=2)
            tk.Label(row,text=label,bg="#171a20",fg=color,font=("Segoe UI Semibold",8),width=12,anchor="w").pack(side="left")
            tk.Label(row,text=f"{counts[key]}",bg="#171a20",fg="#f0f2f5",font=("Segoe UI Semibold",11),width=5,anchor="e").pack(side="left")
            tk.Label(row,text=f"{counts[key]/total:.0%}",bg="#171a20",fg="#747c87",font=("Segoe UI",8),width=7,anchor="e").pack(side="left")
        tk.Label(self.profile_body, text="PARTEIERGEBNISSE  ·  JA / NEIN / ENTHALTEN", bg="#171a20", fg="#7f8792", font=("Segoe UI Semibold",8), anchor="w").pack(fill="x", pady=(12,4))
        for party in PARTIES:
            group=[m for m in self.sim.members if m.party==party]
            if group:
                y=sum(m.vote=="Ja" for m in group); n=sum(m.vote=="Nein" for m in group); e=sum(m.vote=="Enthalten" for m in group)
                tk.Label(self.profile_body,text=f"{party}:  {y} / {n} / {e}",bg="#171a20",fg="#c6cbd2",font=("Segoe UI",7),anchor="w").pack(fill="x",pady=1)
        self.profile_tag.config(text="ERGEBNIS", fg="#aeb4be")

    def start_next_ai_law(self):
        if not self.infinite_mode.get():
            self.sim.running=False; return
        self.status.config(text="KI denkt sich einen neuen Gesetzentwurf aus …")
        def worker():
            try:
                law=Ollama.new_law()
                law=" ".join(law.replace("\n"," ").split()).strip(' ."“”')
                if len(law)<25 or len(law)>500: raise ValueError("ungültiger Entwurf")
            except Exception:
                fallback=[
                    "Der Bund soll ein Programm zur energetischen Sanierung von Schulen auflegen und die Förderung an nachweisbare Einsparungen knüpfen.",
                    "Unternehmen sollen bei der Einführung digitaler Ausbildungsangebote steuerlich gefördert werden, wenn diese dauerhaft Ausbildungsplätze unterstützen.",
                    "Für den öffentlichen Nahverkehr soll ein mehrjähriger Investitionsfonds eingerichtet werden, dessen Mittel nach transparenten Qualitätskriterien vergeben werden.",
                    "Kommunen sollen zusätzliche Mittel für bezahlbaren Wohnraum erhalten, sofern sie verbindliche Konzepte für neue Wohnungen vorlegen.",
                ]
                law=self.sim.rng.choice(fallback)
            self.after(0, lambda:self._begin_next_ai_law(law))
        threading.Thread(target=worker,daemon=True).start()

    def _begin_next_ai_law(self, law):
        if not self.infinite_mode.get():
            self.sim.running=False; return
        self.law_var.set(law); self.law_entry.config(state="disabled")
        self.sim.law=law; self.sim.phase="DEBATTE"; self.sim.round=0; self.sim.amendment=None; self.sim.amendment_passed=False
        self.sim.final_votes={"Ja":0,"Nein":0,"Enthalten":0}; self.sim.amendment_votes={"Ja":0,"Nein":0,"Enthalten":0}
        for m in self.sim.members:
            m.vote=None; m.persuasion=0.0; m.debate_stance=0.0; m.last_reason=""; m.last_vote_score=0.0
        self.current_speech_member=None; self.speech_active=False; self.recent_events=[]
        self.speech_token += 1; self.interruption_token += 1
        self.live.config(state="normal"); self.live.delete("1.0","end"); self.live.config(state="disabled")
        self.log("════════ NEUE SITZUNG ════════")
        self.log("KI-Gesetzentwurf: "+law)
        self.law_meta.config(text="Unendlich-Modus · neue Sitzung")
        self.phase_label.config(text="DEBATTE  0/7"); self.round_label.config(text="0 / 7")
        self.draw_seats(); self.next_step()

    def update_infinite_label(self):
        if self.infinite_mode.get() and not self.sim.running:
            self.status.config(text="∞ Unendlich-Modus aktiv")

    def start(self):
        if self.sim.running: return
        self.sim.running = True; self.paused = False; self.current_speech_member = None; self.speech_active = False
        self.speech_token += 1; self.interruption_token += 1
        self.sim.law = self.law_var.get().strip() or DEFAULT_LAW
        self.sim.phase = "DEBATTE"; self.sim.round = 0; self.sim.max_rounds = 7
        self.sim.amendment = None; self.sim.amendment_passed = False
        self.sim.amendment_votes = {"Ja":0,"Nein":0,"Enthalten":0}; self.sim.final_votes = {"Ja":0,"Nein":0,"Enthalten":0}
        self.sim.law_profile_cache = None
        for m in self.sim.members:
            m.vote = None; m.persuasion = 0; m.debate_stance = 0; m.last_reason = ""
        self.recent_events = []
        self.live.config(state="normal"); self.live.delete("1.0", "end"); self.live.config(state="disabled")
        self.law_entry.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.log("════════ SITZUNG ERÖFFNET ════════")
        self.log("Gesetzentwurf: " + self.sim.law)
        profile = self.sim.law_profile()
        dominant = sorted(profile.items(), key=lambda kv: abs(kv[1]), reverse=True)[:2]
        self.log("Politische Schwerpunkte: " + " · ".join(f"{AXIS_LABELS[a]} {profile[a]:+d}" for a,_ in dominant))
        self.law_meta.config(text="Sitzung läuft · Gesetz wird diskutiert")
        self.phase_label.config(text="DEBATTE  0/7")
        self.round_label.config(text="0 / 7")
        self.next_step()

    def pause(self):
        if not self.sim.running: return
        self.paused = not self.paused
        self.pause_btn.config(text="▶ Weiter" if self.paused else "⏸ Pause")
        self.status.config(text="pausiert" if self.paused else "Simulation läuft …")

    def new_sim(self):
        self.speech_token += 1; self.generation_token += 1; self.interruption_token += 1
        if self.transition_after:
            try:
                self.after_cancel(self.transition_after)
            except Exception:
                pass
            self.transition_after = None
        self.sim = Simulation(); self.paused = False; self.selected_member = None; self.selected_party = None; self.current_speech_member = None; self.speech_active = False
        self.recent_events = []
        self.set_speech(""); self.speaker.config(text="Noch keine Rede"); self.status.config(text="Bereit")
        self.phase_label.config(text="BEREIT"); self.round_label.config(text="0 / 7"); self.law_meta.config(text="Bereit für die erste Sitzung")
        self.pause_btn.config(text="⏸ Pause"); self.start_btn.config(state="normal"); self.law_entry.config(state="normal")
        self.live.config(state="normal"); self.live.delete("1.0", "end"); self.live.config(state="disabled")
        self.draw_seats(); self.show_profile(self.sim.members[0]); self.update_party_counts()


if __name__ == "__main__":
    App().mainloop()
