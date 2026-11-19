# i18n.py
# ---------------------------------------------------------
# Interface language for the chat client.
#
#   tr("Send")                       -> "Enviar" when Spanish is selected
#   tr("{name} is typing…", name=x)  -> placeholders work too
#
# The ENGLISH TEXT IS THE KEY, so the code stays readable and a string
# that has no translation (or a language that has no catalog) simply
# shows in English -- nothing can ever crash or show a blank label.
#
# Your choice is remembered per username in language_prefs.json in the
# same settings folder as theme_prefs.json. It only affects YOUR screen:
# the server and the other people never see which language you picked.
#
# TO ADD A LANGUAGE: add it to LANGUAGES, then add one more column to
# every row of _TABLE (and to _COLUMNS).
# ---------------------------------------------------------

import json
import os

import app_paths

DEFAULT_LANGUAGE = "en"

# code -> name written in that language (this is what the menu shows)
LANGUAGES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
    "it": "Italiano",
}

PREFS_FILE = os.path.join(app_paths.user_data_dir(), "language_prefs.json")
DEFAULT_PREFS = {"language": DEFAULT_LANGUAGE, "translate_messages": True}

# Column order of the rows in _TABLE below (English is the key, so it has no column).
_COLUMNS = ("es", "fr", "de", "pt", "it")

# fmt: off
_TABLE = [
    # ── header buttons / window ───────────────────────────────────────
    ("💰 Wallet", "💰 Cartera", "💰 Portefeuille", "💰 Geldbörse", "💰 Carteira", "💰 Portafoglio"),
    ("⚙ Settings", "⚙ Ajustes", "⚙ Paramètres", "⚙ Einstellungen", "⚙ Configurações", "⚙ Impostazioni"),
    ("🖌 Theme", "🖌 Tema", "🖌 Thème", "🖌 Design", "🖌 Tema", "🖌 Tema"),
    ("🎨 My color", "🎨 Mi color", "🎨 Ma couleur", "🎨 Meine Farbe", "🎨 Minha cor", "🎨 Il mio colore"),
    ("Reset", "Restablecer", "Réinitialiser", "Zurücksetzen", "Redefinir", "Ripristina"),
    ("Log out", "Cerrar sesión", "Se déconnecter", "Abmelden", "Sair", "Esci"),
    ("🌐 Language", "🌐 Idioma", "🌐 Langue", "🌐 Sprache", "🌐 Idioma", "🌐 Lingua"),
    ("Chat Room — {name}", "Sala de chat — {name}", "Salon de discussion — {name}", "Chatraum — {name}", "Sala de bate-papo — {name}", "Chat — {name}"),
    ("Logged in as {name}", "Sesión iniciada como {name}", "Connecté en tant que {name}", "Angemeldet als {name}", "Conectado como {name}", "Connesso come {name}"),
    ("Room", "Sala", "Salon", "Raum", "Sala", "Stanza"),
    ("ONLINE", "EN LÍNEA", "EN LIGNE", "ONLINE", "ONLINE", "ONLINE"),
    ("(you)", "(tú)", "(vous)", "(du)", "(você)", "(tu)"),
    ("Send", "Enviar", "Envoyer", "Senden", "Enviar", "Invia"),
    ("View profile", "Ver perfil", "Voir le profil", "Profil ansehen", "Ver perfil", "Vedi profilo"),
    ("Send message", "Enviar mensaje", "Envoyer un message", "Nachricht senden", "Enviar mensagem", "Invia messaggio"),

    # ── language menu ─────────────────────────────────────────────────
    ("Translate incoming messages", "Traducir mensajes entrantes", "Traduire les messages reçus", "Eingehende Nachrichten übersetzen", "Traduzir mensagens recebidas", "Traduci i messaggi in arrivo"),
    ("Translation isn't set up on this computer. Run:  pip install deep-translator",
     "La traducción no está configurada en este equipo. Ejecuta:  pip install deep-translator",
     "La traduction n'est pas installée sur cet ordinateur. Lancez :  pip install deep-translator",
     "Die Übersetzung ist auf diesem Computer nicht eingerichtet. Führe aus:  pip install deep-translator",
     "A tradução não está configurada neste computador. Execute:  pip install deep-translator",
     "La traduzione non è configurata su questo computer. Esegui:  pip install deep-translator"),
    ("Couldn't translate a message (no internet?). It stays in its original language.",
     "No se pudo traducir un mensaje (¿sin internet?). Se muestra en su idioma original.",
     "Impossible de traduire un message (pas d'internet ?). Il reste dans sa langue d'origine.",
     "Eine Nachricht konnte nicht übersetzt werden (kein Internet?). Sie bleibt in der Originalsprache.",
     "Não foi possível traduzir uma mensagem (sem internet?). Ela continua no idioma original.",
     "Impossibile tradurre un messaggio (niente internet?). Resta nella lingua originale."),

    # ── messages ──────────────────────────────────────────────────────
    ("You", "Tú", "Vous", "Du", "Você", "Tu"),
    ("  ✓✓ Read", "  ✓✓ Leído", "  ✓✓ Lu", "  ✓✓ Gelesen", "  ✓✓ Lida", "  ✓✓ Letto"),
    ("  ✓ Sent", "  ✓ Enviado", "  ✓ Envoyé", "  ✓ Gesendet", "  ✓ Enviada", "  ✓ Inviato"),
    ("[message deleted]", "[mensaje eliminado]", "[message supprimé]", "[Nachricht gelöscht]", "[mensagem apagada]", "[messaggio eliminato]"),
    ("(edited)", "(editado)", "(modifié)", "(bearbeitet)", "(editada)", "(modificato)"),
    ("(translated)", "(traducido)", "(traduit)", "(übersetzt)", "(traduzida)", "(tradotto)"),
    ("{name} is typing…", "{name} está escribiendo…", "{name} écrit…", "{name} schreibt…", "{name} está digitando…", "{name} sta scrivendo…"),
    ("{names} are typing…", "{names} están escribiendo…", "{names} écrivent…", "{names} schreiben…", "{names} estão digitando…", "{names} stanno scrivendo…"),
    ("Editing message — Enter to save, Esc to cancel",
     "Editando mensaje — Enter para guardar, Esc para cancelar",
     "Modification du message — Entrée pour enregistrer, Échap pour annuler",
     "Nachricht bearbeiten — Enter zum Speichern, Esc zum Abbrechen",
     "Editando mensagem — Enter para salvar, Esc para cancelar",
     "Modifica del messaggio — Invio per salvare, Esc per annullare"),
    ("Disconnected from server.", "Desconectado del servidor.", "Déconnecté du serveur.", "Verbindung zum Server getrennt.", "Desconectado do servidor.", "Disconnesso dal server."),
    ("Failed to send -- connection lost.", "No se pudo enviar: se perdió la conexión.", "Échec de l'envoi : connexion perdue.", "Senden fehlgeschlagen – Verbindung verloren.", "Falha ao enviar: conexão perdida.", "Invio non riuscito: connessione persa."),

    # ── right-click menu ──────────────────────────────────────────────
    ("React", "Reaccionar", "Réagir", "Reagieren", "Reagir", "Reagisci"),
    ("More…", "Más…", "Plus…", "Mehr…", "Mais…", "Altro…"),
    ("Edit", "Editar", "Modifier", "Bearbeiten", "Editar", "Modifica"),
    ("Delete", "Eliminar", "Supprimer", "Löschen", "Apagar", "Elimina"),
    ("Download", "Descargar", "Télécharger", "Herunterladen", "Baixar", "Scarica"),
    ("Open file", "Abrir archivo", "Ouvrir le fichier", "Datei öffnen", "Abrir arquivo", "Apri file"),
    ("Show original", "Mostrar original", "Afficher l'original", "Original anzeigen", "Mostrar original", "Mostra originale"),
    ("Show translation", "Mostrar traducción", "Afficher la traduction", "Übersetzung anzeigen", "Mostrar tradução", "Mostra traduzione"),
    ("Delete message", "Eliminar mensaje", "Supprimer le message", "Nachricht löschen", "Apagar mensagem", "Elimina messaggio"),
    ("Delete this message for everyone?", "¿Eliminar este mensaje para todos?", "Supprimer ce message pour tout le monde ?", "Diese Nachricht für alle löschen?", "Apagar esta mensagem para todos?", "Eliminare questo messaggio per tutti?"),
    ("Log out and go back to the login screen?", "¿Cerrar sesión y volver a la pantalla de inicio?", "Se déconnecter et revenir à l'écran de connexion ?", "Abmelden und zum Anmeldebildschirm zurückkehren?", "Sair e voltar para a tela de login?", "Uscire e tornare alla schermata di accesso?"),

    # ── status ────────────────────────────────────────────────────────
    ("Vibing", "De buena onda", "Bien dans ma bulle", "Gut drauf", "Na vibe", "In vena"),
    ("Studying", "Estudiando", "Je révise", "Lernen", "Estudando", "Sto studiando"),
    ("Gaming", "Jugando", "Je joue", "Zocken", "Jogando", "Sto giocando"),
    ("Snack break", "Hora del snack", "Pause snack", "Snackpause", "Hora do lanche", "Pausa snack"),
    ("Napping", "Echando siesta", "Je fais la sieste", "Nickerchen", "Cochilando", "Pisolino"),
    ("Locked in", "Concentrado", "Concentré", "Fokussiert", "Concentrado", "Concentrato"),
    ("Ghost mode", "Modo fantasma", "Mode fantôme", "Geistermodus", "Modo fantasma", "Modalità fantasma"),
    ("Zoning out", "Distraído", "Dans la lune", "Abwesend", "Distraído", "Sovrappensiero"),
    ("Active -- around and happy to chat", "Activo: por aquí y con ganas de charlar", "Actif : là et content de discuter", "Aktiv – da und zum Chatten bereit", "Ativo: por aqui e com vontade de conversar", "Attivo: ci sono e ho voglia di chiacchierare"),
    ("Busy with the books", "Ocupado con los libros", "Le nez dans les livres", "Beschäftigt mit Lernen", "Ocupado com os livros", "Impegnato con i libri"),
    ("In the zone", "En su mundo", "Dans ma bulle", "Voll konzentriert", "Focado no jogo", "Nella zona"),
    ("Back in a few", "Vuelvo en un rato", "Je reviens dans quelques minutes", "Gleich wieder da", "Já volto", "Torno tra poco"),
    ("Away -- might take a while to answer", "Ausente: puede tardar en responder", "Absent : je mettrai peut-être du temps à répondre", "Abwesend – Antwort kann dauern", "Ausente: pode demorar para responder", "Assente: potrei metterci un po' a rispondere"),
    ("Do Not Disturb -- no notification sounds", "No molestar: sin sonidos de notificación", "Ne pas déranger : pas de sons de notification", "Bitte nicht stören – keine Benachrichtigungstöne", "Não perturbe: sem sons de notificação", "Non disturbare: nessun suono di notifica"),
    ("Appear offline to everyone", "Aparecer sin conexión para todos", "Apparaître hors ligne pour tout le monde", "Für alle offline erscheinen", "Aparecer offline para todos", "Appari offline a tutti"),
    ("Idle -- no activity for a while (automatic)", "Inactivo: sin actividad desde hace un rato (automático)", "Inactif : aucune activité depuis un moment (automatique)", "Inaktiv – seit einer Weile nichts los (automatisch)", "Inativo: sem atividade há algum tempo (automático)", "Inattivo: nessuna attività da un po' (automatico)"),
    ("✏  Add a note to my status…", "✏  Añadir una nota a mi estado…", "✏  Ajouter une note à mon statut…", "✏  Notiz zu meinem Status hinzufügen…", "✏  Adicionar uma nota ao meu status…", "✏  Aggiungi una nota al mio stato…"),

    # ── settings: tabs and shared bits ───────────────────────────────
    ("Settings", "Ajustes", "Paramètres", "Einstellungen", "Configurações", "Impostazioni"),
    ("Picture", "Foto", "Photo", "Bild", "Foto", "Foto"),
    ("Theme", "Tema", "Thème", "Design", "Tema", "Tema"),
    ("Profile card", "Tarjeta de perfil", "Carte de profil", "Profilkarte", "Cartão de perfil", "Scheda profilo"),
    ("Account", "Cuenta", "Compte", "Konto", "Conta", "Account"),
    ("Security", "Seguridad", "Sécurité", "Sicherheit", "Segurança", "Sicurezza"),
    ("Your current password", "Tu contraseña actual", "Votre mot de passe actuel", "Dein aktuelles Passwort", "Sua senha atual", "La tua password attuale"),

    # ── settings: picture tab ────────────────────────────────────────
    ("Your profile picture", "Tu foto de perfil", "Votre photo de profil", "Dein Profilbild", "Sua foto de perfil", "La tua foto profilo"),
    ("Choose picture...", "Elegir foto...", "Choisir une photo...", "Bild auswählen...", "Escolher foto...", "Scegli foto..."),
    ("Remove picture", "Quitar foto", "Supprimer la photo", "Bild entfernen", "Remover foto", "Rimuovi foto"),
    ("Any image works: it's cropped to a square and shrunk.\nEveryone in the chat sees it next to your name.",
     "Sirve cualquier imagen: se recorta a un cuadrado y se reduce.\nTodos en el chat la ven junto a tu nombre.",
     "Toute image convient : elle est recadrée en carré et réduite.\nTout le monde la voit à côté de votre nom.",
     "Jedes Bild funktioniert: Es wird quadratisch zugeschnitten und verkleinert.\nAlle im Chat sehen es neben deinem Namen.",
     "Qualquer imagem serve: ela é cortada em quadrado e reduzida.\nTodos no chat a veem ao lado do seu nome.",
     "Va bene qualsiasi immagine: viene ritagliata in un quadrato e rimpicciolita.\nTutti nella chat la vedono accanto al tuo nome."),

    # ── settings: theme tab ──────────────────────────────────────────
    ("Make the chat yours", "Personaliza el chat", "Personnalisez le chat", "Mach den Chat zu deinem", "Deixe o chat com a sua cara", "Rendi la chat tua"),
    ("Themes only change how the chat looks on YOUR screen.", "Los temas solo cambian el aspecto del chat en TU pantalla.", "Les thèmes ne changent l'apparence du chat que sur VOTRE écran.", "Designs ändern das Aussehen nur auf DEINEM Bildschirm.", "Os temas só mudam a aparência do chat na SUA tela.", "I temi cambiano l'aspetto della chat solo sul TUO schermo."),
    ("Accent color", "Color de acento", "Couleur d'accent", "Akzentfarbe", "Cor de destaque", "Colore d'accento"),
    ("Chat background", "Fondo del chat", "Fond du chat", "Chat-Hintergrund", "Fundo do chat", "Sfondo della chat"),
    ("Pick...", "Elegir...", "Choisir...", "Wählen...", "Escolher...", "Scegli..."),
    ("Use theme's", "Usar el del tema", "Celle du thème", "Vom Design", "Usar a do tema", "Usa quello del tema"),
    ("Font", "Fuente", "Police", "Schriftart", "Fonte", "Carattere"),
    ("Text size", "Tamaño del texto", "Taille du texte", "Textgröße", "Tamanho do texto", "Dimensione del testo"),
    ("Spacing", "Espaciado", "Espacement", "Abstand", "Espaçamento", "Spaziatura"),
    ("Preview", "Vista previa", "Aperçu", "Vorschau", "Pré-visualização", "Anteprima"),
    ("Reset to default look", "Restablecer el aspecto original", "Rétablir l'apparence par défaut", "Auf Standard zurücksetzen", "Restaurar o visual padrão", "Ripristina l'aspetto predefinito"),

    # ── settings: profile card tab ───────────────────────────────────
    ("Your profile card", "Tu tarjeta de perfil", "Votre carte de profil", "Deine Profilkarte", "Seu cartão de perfil", "La tua scheda profilo"),
    ("This is what people see when they click your name.", "Esto es lo que ven los demás al hacer clic en tu nombre.", "C'est ce que les autres voient en cliquant sur votre nom.", "Das sehen andere, wenn sie auf deinen Namen klicken.", "É isto que as pessoas veem ao clicar no seu nome.", "È ciò che gli altri vedono cliccando sul tuo nome."),
    ("About me", "Sobre mí", "À propos de moi", "Über mich", "Sobre mim", "Su di me"),
    ("Pronouns", "Pronombres", "Pronoms", "Pronomen", "Pronomes", "Pronomi"),
    ("Badge", "Insignia", "Badge", "Abzeichen", "Distintivo", "Distintivo"),
    ("Pick…", "Elegir…", "Choisir…", "Wählen…", "Escolher…", "Scegli…"),
    ("Card color", "Color de la tarjeta", "Couleur de la carte", "Kartenfarbe", "Cor do cartão", "Colore della scheda"),
    ("Choose…", "Elegir…", "Choisir…", "Wählen…", "Escolher…", "Scegli…"),
    ("Default", "Por defecto", "Par défaut", "Standard", "Padrão", "Predefinito"),
    ("Save my card", "Guardar mi tarjeta", "Enregistrer ma carte", "Meine Karte speichern", "Salvar meu cartão", "Salva la mia scheda"),
    ("Loading your card…", "Cargando tu tarjeta…", "Chargement de votre carte…", "Deine Karte wird geladen…", "Carregando seu cartão…", "Caricamento della scheda…"),

    # ── settings: account tab ────────────────────────────────────────
    ("Confirm it's you", "Confirma que eres tú", "Confirmez que c'est vous", "Bestätige, dass du es bist", "Confirme que é você", "Conferma che sei tu"),
    ("Your current password (for {name})", "Tu contraseña actual (de {name})", "Votre mot de passe actuel (pour {name})", "Dein aktuelles Passwort (für {name})", "Sua senha atual (de {name})", "La tua password attuale (di {name})"),
    ("Show passwords", "Mostrar contraseñas", "Afficher les mots de passe", "Passwörter anzeigen", "Mostrar senhas", "Mostra le password"),
    ("Change username", "Cambiar nombre de usuario", "Changer de nom d'utilisateur", "Benutzernamen ändern", "Alterar nome de usuário", "Cambia nome utente"),
    ("New username", "Nuevo nombre de usuario", "Nouveau nom d'utilisateur", "Neuer Benutzername", "Novo nome de usuário", "Nuovo nome utente"),
    ("3-30 characters: letters, numbers, underscores.\nYou'll be asked to log in again afterwards.",
     "3-30 caracteres: letras, números y guiones bajos.\nDespués tendrás que iniciar sesión de nuevo.",
     "3 à 30 caractères : lettres, chiffres, tirets bas.\nVous devrez ensuite vous reconnecter.",
     "3–30 Zeichen: Buchstaben, Zahlen, Unterstriche.\nDanach musst du dich erneut anmelden.",
     "3-30 caracteres: letras, números e sublinhados.\nDepois você precisará entrar novamente.",
     "3-30 caratteri: lettere, numeri, trattini bassi.\nDopo dovrai accedere di nuovo."),
    ("Change password", "Cambiar contraseña", "Changer de mot de passe", "Passwort ändern", "Alterar senha", "Cambia password"),
    ("New password", "Nueva contraseña", "Nouveau mot de passe", "Neues Passwort", "Nova senha", "Nuova password"),
    ("Confirm new password", "Confirmar nueva contraseña", "Confirmer le nouveau mot de passe", "Neues Passwort bestätigen", "Confirmar nova senha", "Conferma nuova password"),

    # ── settings: security tab ───────────────────────────────────────
    ("If you forget your password, these let you reset it.", "Si olvidas tu contraseña, esto te permite restablecerla.", "Si vous oubliez votre mot de passe, ceci vous permet de le réinitialiser.", "Wenn du dein Passwort vergisst, kannst du es damit zurücksetzen.", "Se você esquecer a senha, isto permite redefini-la.", "Se dimentichi la password, queste domande ti permettono di reimpostarla."),
    ("Question {n}", "Pregunta {n}", "Question {n}", "Frage {n}", "Pergunta {n}", "Domanda {n}"),
    ("Answers aren't case-sensitive and are never shown again.\nTo change a question, type all three answers again.",
     "Las respuestas no distinguen mayúsculas y nunca se vuelven a mostrar.\nPara cambiar una pregunta, escribe las tres respuestas de nuevo.",
     "Les réponses ne tiennent pas compte de la casse et ne sont jamais réaffichées.\nPour changer une question, saisissez à nouveau les trois réponses.",
     "Groß-/Kleinschreibung spielt keine Rolle; Antworten werden nie wieder angezeigt.\nUm eine Frage zu ändern, gib alle drei Antworten erneut ein.",
     "As respostas não diferenciam maiúsculas e nunca são exibidas novamente.\nPara mudar uma pergunta, digite as três respostas de novo.",
     "Le risposte non distinguono maiuscole e minuscole e non vengono più mostrate.\nPer cambiare una domanda, digita di nuovo tutte e tre le risposte."),
    ("Save security questions", "Guardar preguntas de seguridad", "Enregistrer les questions de sécurité", "Sicherheitsfragen speichern", "Salvar perguntas de segurança", "Salva le domande di sicurezza"),

    # ── settings: delete tab ─────────────────────────────────────────
    ("Delete", "Eliminar", "Supprimer", "Löschen", "Apagar", "Elimina"),
    ("Delete your account", "Eliminar tu cuenta", "Supprimer votre compte", "Dein Konto löschen", "Excluir sua conta", "Elimina il tuo account"),
    ("This is permanent and can't be undone.\n\nWhat gets deleted:\n   \u2022 your account, password and security questions\n   \u2022 every message and file you sent, for everyone\n   \u2022 private messages other people sent you\n   \u2022 your reactions and profile picture\n\nYour username becomes free for anyone to register.",
     "Esto es permanente y no se puede deshacer.\n\nQué se elimina:\n   \u2022 tu cuenta, contraseña y preguntas de seguridad\n   \u2022 todos los mensajes y archivos que enviaste, para todos\n   \u2022 los mensajes privados que te enviaron\n   \u2022 tus reacciones y tu foto de perfil\n\nTu nombre de usuario quedará libre para que cualquiera lo registre.",
     "C'est définitif et irréversible.\n\nCe qui est supprimé :\n   \u2022 votre compte, mot de passe et questions de sécurité\n   \u2022 tous les messages et fichiers que vous avez envoyés, pour tout le monde\n   \u2022 les messages privés que d'autres vous ont envoyés\n   \u2022 vos réactions et votre photo de profil\n\nVotre nom d'utilisateur redevient libre pour que n'importe qui puisse l'utiliser.",
     "Das ist endgültig und kann nicht rückgängig gemacht werden.\n\nWas gelöscht wird:\n   \u2022 dein Konto, Passwort und deine Sicherheitsfragen\n   \u2022 alle Nachrichten und Dateien, die du gesendet hast – für alle\n   \u2022 private Nachrichten, die andere dir geschickt haben\n   \u2022 deine Reaktionen und dein Profilbild\n\nDein Benutzername wird frei und kann von jedem neu registriert werden.",
     "Isto é permanente e não pode ser desfeito.\n\nO que será apagado:\n   \u2022 sua conta, senha e perguntas de segurança\n   \u2022 todas as mensagens e arquivos que você enviou, para todos\n   \u2022 mensagens privadas que outras pessoas enviaram a você\n   \u2022 suas reações e sua foto de perfil\n\nSeu nome de usuário ficará livre para qualquer pessoa registrar.",
     "È permanente e non si può annullare.\n\nCosa viene eliminato:\n   \u2022 il tuo account, la password e le domande di sicurezza\n   \u2022 ogni messaggio e file che hai inviato, per tutti\n   \u2022 i messaggi privati che gli altri ti hanno inviato\n   \u2022 le tue reazioni e la foto profilo\n\nIl tuo nome utente tornerà libero e chiunque potrà registrarlo."),
    ("Type your username ({name}) to confirm", "Escribe tu nombre de usuario ({name}) para confirmar", "Saisissez votre nom d'utilisateur ({name}) pour confirmer", "Gib zur Bestätigung deinen Benutzernamen ({name}) ein", "Digite seu nome de usuário ({name}) para confirmar", "Digita il tuo nome utente ({name}) per confermare"),
    ("Delete my account permanently", "Eliminar mi cuenta para siempre", "Supprimer mon compte définitivement", "Mein Konto endgültig löschen", "Excluir minha conta permanentemente", "Elimina il mio account definitivamente"),
]
# fmt: on

# English text -> {language code: translation}
_CATALOG: dict[str, dict[str, str]] = {}
for _row in _TABLE:
    assert len(_row) == len(_COLUMNS) + 1, f"bad i18n row: {_row[0]!r}"
    _CATALOG[_row[0]] = dict(zip(_COLUMNS, _row[1:]))

_current = DEFAULT_LANGUAGE


def available() -> dict[str, str]:
    return dict(LANGUAGES)


def current_language() -> str:
    return _current


def set_language(code: str) -> str:
    """Switch the interface language. Unknown codes fall back to English."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def tr(text: str, **fmt) -> str:
    """Translate `text` into the current interface language (English if there's no translation)."""
    out = text
    if _current != DEFAULT_LANGUAGE:
        out = _CATALOG.get(text, {}).get(_current, text)
    if fmt:
        try:
            out = out.format(**fmt)
        except (KeyError, IndexError, ValueError):
            out = text.format(**fmt) if text else text   # a bad translation must never crash the UI
    return out


# ─────────────────────────────────────────────────────────────
# remembering your choice (per username, on this computer only)
# ─────────────────────────────────────────────────────────────
def _read_all() -> dict:
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_prefs(raw) -> dict:
    prefs = dict(DEFAULT_PREFS)
    if isinstance(raw, dict):
        if raw.get("language") in LANGUAGES:
            prefs["language"] = raw["language"]
        if isinstance(raw.get("translate_messages"), bool):
            prefs["translate_messages"] = raw["translate_messages"]
    return prefs


def load_prefs(username: str) -> dict:
    return clean_prefs(_read_all().get(username.lower()))


def save_prefs(username: str, prefs: dict) -> None:
    data = _read_all()
    data[username.lower()] = clean_prefs(prefs)
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass   # can't write the file -> the choice just won't be remembered next time
