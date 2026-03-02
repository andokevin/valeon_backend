# app/core/orchestrator/image_orchestrator.py (CORRIGÉ - français)
from typing import Dict, Any, Optional
import logging
import os
import re
from app.core.modules.gemini import GeminiClient
from app.core.modules.spotify.client import SpotifyClient
from app.core.modules.tmdb.client import TMDBClient
from app.core.modules.justwatch.client import JustWatchClient
from app.core.modules.youtube.client import YouTubeClient
from app.core.config import settings
from app.models import User

logger = logging.getLogger(__name__)

class ImageOrchestrator:
    def __init__(self):
        self.gemini = GeminiClient()
        self.spotify = SpotifyClient() if settings.SPOTIFY_ENABLED else None
        self.tmdb = TMDBClient() if settings.TMDB_ENABLED else None
        self.justwatch = JustWatchClient() if settings.JUSTWATCH_ENABLED else None
        self.youtube = YouTubeClient() if settings.YOUTUBE_ENABLED else None

    async def process_image(self, file_path: str, user: User, db) -> Dict[str, Any]:
        logger.info(f"ImageOrchestrator: Analyse de {os.path.basename(file_path)}")
        
        try:
            # ===== ÉTAPE 1: PROMPT GEMINI AMÉLIORÉ AVEC INSTRUCTION FRANÇAIS =====
            prompt = """
            Tu es un expert en identification de célébrités et de contenus culturels (musique, films, séries).

            **IMPORTANT: Tu dois TOUJOURS répondre en FRANÇAIS.**
            
            RÈGLE ABSOLUE: Ta réponse finale doit être une phrase naturelle commençant par:
            - "C'est une chanson de ... dans l'album ..." (pour la musique)
            - "C'est un film avec ... réalisé par ..." (pour les films)
            - "C'est une photo de ..." (pour les célébrités)

            Analyse cette image avec la PLUS GRANDE PRÉCISION possible.

            TYPES DE CONTENU POSSIBLES:
            - "celebrity_photo": Photo d'une ou plusieurs célébrités
            - "album_cover": Pochette d'album (avec titre et nom d'artiste)
            - "movie_poster": Affiche de film (avec titre, acteurs, réalisateur)
            - "movie_scene": Scène de film (capture d'écran)
            - "music_video": Clip musical (image extraite d'un clip)
            - "concert_photo": Photo de concert
            - "tv_show_scene": Scène de série TV
            - "interview_photo": Photo d'interview (journaliste + célébrité)
            - "press_conference": Conférence de presse
            - "red_carpet": Photo de tapis rouge/événement
            - "unknown": Type non identifiable

            RÈGLES D'IDENTIFICATION DES CÉLÉBRITÉS:
            1. Identifie CHAQUE personne visible avec son nom COMPLET et précis
            2. Détermine son métier principal avec précision:
               - "singer" (chanteur) - pour les artistes musicaux
               - "actor" (acteur) - pour les comédiens
               - "both" (les deux) - pour ceux qui chantent ET jouent (ex: Lady Gaga, Jared Leto)
               - "musician" (musicien) - pour les instrumentistes
               - "journalist" (journaliste) - pour les intervieweurs
               - "director" (réalisateur) - pour les réalisateurs
               - "producer" (producteur) - pour les producteurs
               - "sportsperson" (sportif) - pour les athlètes
               - "politician" (politicien) - pour les personnalités politiques
               - "other" - autre profession

            3. CAS PARTICULIERS À RECONNAÎTRE:
               - Si tu vois UN CHANTEUR et UN ACTEUR ensemble (ex: Lady Gaga + Bradley Cooper) → recherche le film musical et sa chanson (ex: "Shallow" de "A Star Is Born")
               - Si tu vois DEUX CHANTEURS ensemble → recherche le featuring musical (ex: Shawn Mendes + Camila Cabello → "Señorita")
               - Si tu vois UN CHANTEUR seul avec un micro → recherche sa chanson la plus populaire
               - Si tu vois DES ACTEURS seuls → recherche leur film le plus connu
               - Si tu vois UN JOURNALISTE avec une célébrité → recherche l'interview/émission
               - Si tu vois une image de DOSSIER/ARCHIVE → précise-le

            4. UTILISE LE CONTEXTE VISUEL:
               - Micro, scène, instruments → musique/concert
               - Costumes d'époque, décors de film → film/série
               - Tapis rouge, flashs → événement/red carpet
               - Studio, micro-cravate → interview
               - Vêtements formels, pupitre → conférence de presse

            Réponds UNIQUEMENT en JSON avec cette structure DÉTAILLÉE:
            {
                "content_type": "celebrity_photo" ou autre type,
                "subtype": "red_carpet" ou "interview" ou "concert" ou "backstage" ou "studio" ou "candid" (optionnel),
                "celebrities": [
                    {
                        "name": "nom complet de la célébrité",
                        "profession": "singer/actor/both/musician/journalist/etc",
                        "known_for": ["titre1", "titre2"] (œuvres connues, optionnel),
                        "role_in_image": "sujet principal" ou "secondaire" (optionnel)
                    }
                ],
                "title": "titre du film/album/chanson visible sur l'image",
                "artist": "nom de l'artiste/chanteur principal",
                "director": "nom du réalisateur (pour films)",
                "actors": ["acteur 1", "acteur 2"] (si visibles sur l'affiche),
                "song_name": "nom de la chanson (si clip musical ou featuring)",
                "album_name": "nom de l'album (si pochette)",
                "movie_name": "titre du film (si affiche ou scène)",
                "interview_with": "nom de la personne interviewée" (si interview),
                "interviewer": "nom du journaliste" (si interview),
                "event_name": "nom de l'événement" (si red carpet, cérémonie),
                "year": "année (format YYYY)",
                "genre": "genre musical ou cinématographique",
                "description": "description précise de la scène/de l'image en français",
                "text_detected": "tout le texte visible sur l'image",
                "confidence": 0.0-1.0 (basé sur la lisibilité),
                "reasoning": "explication courte en français de pourquoi cette identification",
                "suggested_searches": [
                    "recherche prioritaire 1",
                    "recherche prioritaire 2"
                ],
                "action_needed": "spotify" ou "tmdb" ou "youtube" ou "none"
            }

            EXEMPLES DÉTAILLÉS EN FRANÇAIS:

            1. Lady Gaga et Bradley Cooper (A Star Is Born):
            {
                "content_type": "celebrity_photo",
                "subtype": "movie_scene",
                "celebrities": [
                    {"name": "Lady Gaga", "profession": "both", "known_for": ["Shallow", "Poker Face", "A Star Is Born"]},
                    {"name": "Bradley Cooper", "profession": "actor", "known_for": ["A Star Is Born", "Silver Linings Playbook"]}
                ],
                "movie_name": "A Star Is Born",
                "song_name": "Shallow",
                "year": "2018",
                "genre": "Drame musical",
                "description": "Lady Gaga et Bradley Cooper dans une scène du film A Star Is Born où ils jouent sur scène",
                "confidence": 0.95,
                "reasoning": "Lady Gaga (chanteuse/actrice) et Bradley Cooper (acteur) sont célèbres pour ce film musical et la chanson Shallow",
                "suggested_searches": ["A Star Is Born Shallow", "Lady Gaga Bradley Cooper duet"],
                "action_needed": "spotify"
            }

            2. Shawn Mendes et Camila Cabello:
            {
                "content_type": "celebrity_photo",
                "subtype": "music_video",
                "celebrities": [
                    {"name": "Shawn Mendes", "profession": "singer"},
                    {"name": "Camila Cabello", "profession": "singer"}
                ],
                "song_name": "Señorita",
                "year": "2019",
                "genre": "Pop",
                "description": "Shawn Mendes et Camila Cabello dans le clip de Señorita",
                "confidence": 0.95,
                "reasoning": "Deux chanteurs ensemble → featuring musical Señorita",
                "suggested_searches": ["Shawn Mendes Camila Cabello Señorita"],
                "action_needed": "spotify"
            }

            3. Beyoncé seule sur scène:
            {
                "content_type": "celebrity_photo",
                "subtype": "concert",
                "celebrities": [
                    {"name": "Beyoncé", "profession": "singer"}
                ],
                "artist": "Beyoncé",
                "description": "Beyoncé performant sur scène lors d'un concert",
                "confidence": 0.9,
                "reasoning": "Beyoncé est une chanteuse mondialement connue, ici en concert",
                "suggested_searches": ["Beyoncé concert", "Beyoncé live"],
                "action_needed": "spotify"
            }

            4. Journaliste interviewant Dwayne Johnson:
            {
                "content_type": "celebrity_photo",
                "subtype": "interview",
                "celebrities": [
                    {"name": "Dwayne Johnson", "profession": "actor"},
                    {"name": "Jimmy Fallon", "profession": "journalist"}
                ],
                "interview_with": "Dwayne Johnson",
                "interviewer": "Jimmy Fallon",
                "event_name": "The Tonight Show",
                "description": "Dwayne Johnson interviewé par Jimmy Fallon au Tonight Show",
                "confidence": 0.85,
                "reasoning": "Dwayne Johnson (acteur) avec Jimmy Fallon (présentateur) dans un studio de talk-show",
                "suggested_searches": ["Dwayne Johnson Jimmy Fallon interview"],
                "action_needed": "youtube"
            }
            """
            
            logger.info("ImageOrchestrator: Analyse Gemini Vision (prompt amélioré)...")
            
            # Appel Gemini
            vision_result = await self.gemini.generate_with_images(
                prompt=prompt,
                image_paths=[file_path],
                max_tokens=1500,
                json_mode=True
            )
            
            # Extraire les données améliorées
            content_type = vision_result.get("content_type", "unknown")
            subtype = vision_result.get("subtype", "")
            celebrities_data = vision_result.get("celebrities", [])
            title = vision_result.get("title")
            artist = vision_result.get("artist")
            director = vision_result.get("director")
            actors = vision_result.get("actors", [])
            song_name = vision_result.get("song_name")
            album_name = vision_result.get("album_name")
            movie_name = vision_result.get("movie_name")
            interview_with = vision_result.get("interview_with")
            interviewer = vision_result.get("interviewer")
            event_name = vision_result.get("event_name")
            year = vision_result.get("year")
            genre = vision_result.get("genre")
            description = vision_result.get("description", "")
            text_detected = vision_result.get("text_detected", "")
            confidence = vision_result.get("confidence", 0.5)
            reasoning = vision_result.get("reasoning", "")
            suggested_searches = vision_result.get("suggested_searches", [])
            action_needed = vision_result.get("action_needed", "none")
            
            # Formater les célébrités pour les logs
            celebrities_names = [c.get("name") for c in celebrities_data if isinstance(c, dict)]
            celebrities_professions = {c.get("name"): c.get("profession") for c in celebrities_data if isinstance(c, dict)}
            
            logger.info(f"ImageOrchestrator: Type détecté = {content_type}" + (f" ({subtype})" if subtype else ""))
            if celebrities_names:
                logger.info(f"🎭 Célébrités identifiées: {celebrities_names}")
                for name, prof in celebrities_professions.items():
                    logger.info(f"   - {name}: {prof}")
            if reasoning:
                logger.info(f"🔍 Raisonnement: {reasoning}")
            
            # ===== ÉTAPE 2: RÉSULTAT DE BASE AMÉLIORÉ =====
            result = {
                "type": content_type,
                "subtype": subtype,
                "celebrities": celebrities_data,
                "celebrities_names": celebrities_names,
                "title": title or song_name or movie_name,
                "artist": artist,
                "director": director,
                "actors": actors,
                "song_name": song_name,
                "album": album_name,
                "movie_name": movie_name,
                "interview_with": interview_with,
                "interviewer": interviewer,
                "event_name": event_name,
                "year": year,
                "genre": genre,
                "description": description,
                "text_detected": text_detected,
                "confidence": confidence,
                "reasoning": reasoning,
                "suggested_searches": suggested_searches,
                "detection": {
                    "method": "gemini_vision_enhanced",
                    "confidence": confidence,
                    "content_type": content_type,
                    "subtype": subtype
                }
            }
            
            # ===== ÉTAPE 3: ENRICHISSEMENT INTELLIGENT AMÉLIORÉ =====
            
            # ✅ CAS SPÉCIAL: Chanteur + Acteur (film musical)
            singers = [c for c in celebrities_data if c.get("profession") in ["singer", "both"]]
            actors_celeb = [c for c in celebrities_data if c.get("profession") in ["actor", "both"]]
            
            # CAS 1: Un chanteur et un acteur (ex: Lady Gaga + Bradley Cooper)
            if len(singers) >= 1 and len(actors_celeb) >= 1 and content_type == "celebrity_photo":
                logger.info(f"🎬 Détection chanteur + acteur: film musical probable")
                
                # Chercher d'abord le titre du film suggéré par Gemini
                search_terms = []
                if movie_name:
                    search_terms.append(movie_name)
                if suggested_searches:
                    search_terms.extend(suggested_searches)
                if song_name:
                    search_terms.append(song_name)
                
                # Recherche TMDB pour le film
                if self.tmdb:
                    for term in search_terms:
                        if term:
                            logger.info(f"ImageOrchestrator: Recherche TMDB: '{term}'")
                            tmdb_result = await self.tmdb.search_movie(term, year)
                            if tmdb_result:
                                result["tmdb"] = tmdb_result
                                result["image"] = tmdb_result.get("image") or result.get("image")
                                result["title"] = tmdb_result.get("title")
                                result["movie_name"] = tmdb_result.get("title")
                                result["director"] = tmdb_result.get("director")
                                result["year"] = tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else year
                                result["description"] = tmdb_result.get("description")
                                logger.info(f"✅ Film trouvé: {tmdb_result.get('title')}")
                                
                                # Trailer YouTube
                                if self.youtube:
                                    youtube_result = await self.youtube.search_trailer(
                                        tmdb_result.get("title", ""),
                                        result.get("year")
                                    )
                                    if youtube_result:
                                        result["youtube"] = youtube_result
                                        result.setdefault("external_links", {})
                                        result["external_links"]["youtube"] = youtube_result.get("url")
                                break
                
                # Recherche Spotify pour la chanson (si film musical)
                if self.spotify and song_name:
                    logger.info(f"ImageOrchestrator: Recherche Spotify chanson: '{song_name}'")
                    tracks = await self.spotify.search_track(song_name, limit=3)
                    if tracks:
                        for track in tracks:
                            track_artists = track.get("artists", "").lower()
                            singer_names = [s.get("name", "").lower() for s in singers]
                            if all(any(s in track_artists for s in singer_names) for singer in singer_names):
                                result["spotify"] = track
                                result["image"] = track.get("image") or result.get("image")
                                result["song_name"] = track.get("title")
                                logger.info(f"✅ Chanson trouvée: {track.get('title')}")
                                break
                        if not result.get("spotify") and tracks:
                            result["spotify"] = tracks[0]
            
            # CAS 2: Deux chanteurs (featuring musical)
            elif len(singers) >= 2 and content_type == "celebrity_photo":
                logger.info(f"🎵 Détection de featuring musical avec {len(singers)} chanteurs")
                
                singer_names = [s.get("name") for s in singers]
                search_terms = [
                    song_name,
                    f"{singer_names[0]} {singer_names[1]}",
                    f"{singer_names[0]} {singer_names[1]} song",
                    f"{singer_names[0]} {singer_names[1]} duet"
                ] + (suggested_searches if suggested_searches else [])
                
                if self.spotify:
                    for term in search_terms:
                        if term:
                            logger.info(f"ImageOrchestrator: Recherche Spotify: '{term}'")
                            tracks = await self.spotify.search_track(term, limit=5)
                            if tracks:
                                # Chercher une chanson avec les deux artistes
                                for track in tracks:
                                    track_artists = track.get("artists", "").lower()
                                    if all(s.lower() in track_artists for s in singer_names):
                                        result["spotify"] = track
                                        result["image"] = track.get("image")
                                        result["title"] = track.get("title")
                                        result["artist"] = track.get("artist")
                                        result["song_name"] = track.get("title")
                                        result["year"] = track.get("release_date", "")[:4] if track.get("release_date") else year
                                        logger.info(f"✅ Featuring trouvé: {track.get('title')} - {track.get('artist')}")
                                        break
                                
                                if not result.get("spotify") and tracks:
                                    result["spotify"] = tracks[0]
                                    logger.info(f"✅ Piste trouvée: {tracks[0].get('title')}")
                                
                                if result.get("spotify") and self.youtube:
                                    youtube_result = await self.youtube.search_music_video(
                                        result.get("title") or result.get("song_name"),
                                        result.get("artist") or singer_names[0]
                                    )
                                    if youtube_result:
                                        result["youtube"] = youtube_result
                                        result.setdefault("external_links", {})
                                        result["external_links"]["youtube"] = youtube_result.get("url")
                                break
            
            # CAS 3: Acteurs seuls (recherche film)
            elif len(actors_celeb) >= 1 and len(singers) == 0 and content_type == "celebrity_photo":
                logger.info(f"🎬 Détection d'acteurs seuls, recherche film")
                
                actor_names = [a.get("name") for a in actors_celeb]
                search_terms = [
                    movie_name,
                    f"{actor_names[0]} movie",
                    f"{actor_names[0]} {actor_names[1] if len(actor_names) > 1 else ''} movie".strip(),
                    ' '.join(actor_names[:2]) + " film"
                ] + (suggested_searches if suggested_searches else [])
                
                if self.tmdb:
                    for term in search_terms:
                        if term:
                            logger.info(f"ImageOrchestrator: Recherche TMDB: '{term}'")
                            tmdb_result = await self.tmdb.search_movie(term, year)
                            if tmdb_result:
                                result["tmdb"] = tmdb_result
                                result["image"] = tmdb_result.get("image") or result.get("image")
                                result["title"] = tmdb_result.get("title")
                                result["movie_name"] = tmdb_result.get("title")
                                result["director"] = tmdb_result.get("director")
                                result["actors"] = tmdb_result.get("cast", [])[:3]
                                result["year"] = tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else year
                                result["description"] = tmdb_result.get("description")
                                logger.info(f"✅ Film trouvé: {tmdb_result.get('title')}")
                                
                                if self.youtube:
                                    youtube_result = await self.youtube.search_trailer(
                                        tmdb_result.get("title", ""),
                                        result.get("year")
                                    )
                                    if youtube_result:
                                        result["youtube"] = youtube_result
                                        result.setdefault("external_links", {})
                                        result["external_links"]["youtube"] = youtube_result.get("url")
                                break
            
            # CAS 4: Chanteur seul
            elif len(singers) == 1 and len(actors_celeb) == 0 and content_type == "celebrity_photo":
                logger.info(f"🎤 Détection d'un chanteur seul")
                
                singer_name = singers[0].get("name")
                search_terms = [
                    song_name,
                    f"{singer_name} top tracks",
                    f"{singer_name} popular songs"
                ] + (suggested_searches if suggested_searches else [])
                
                if self.spotify:
                    logger.info(f"ImageOrchestrator: Recherche Spotify pour '{singer_name}'")
                    
                    # Chercher d'abord un album récent
                    albums = await self.spotify.search_album(singer_name)
                    if albums:
                        result["spotify"] = albums
                        result["image"] = albums.get("image")
                        result["artist"] = singer_name
                        result["title"] = albums.get("title")
                        result["album"] = albums.get("title")
                        result["year"] = albums.get("release_date", "")[:4] if albums.get("release_date") else None
                        logger.info(f"✅ Album trouvé: {albums.get('title')}")
                    else:
                        # Chercher les tops tracks
                        for term in search_terms:
                            if term:
                                tracks = await self.spotify.search_track(term, limit=5)
                                if tracks:
                                    result["spotify"] = tracks[0]
                                    result["image"] = tracks[0].get("image")
                                    result["artist"] = singer_name
                                    result["title"] = tracks[0].get("title")
                                    result["song_name"] = tracks[0].get("title")
                                    logger.info(f"✅ Track trouvé: {tracks[0].get('title')}")
                                    break
                    
                    if result.get("spotify") and self.youtube:
                        youtube_result = await self.youtube.search_music_video(
                            result.get("title") or result.get("song_name") or singer_name,
                            singer_name
                        )
                        if youtube_result:
                            result["youtube"] = youtube_result
                            result.setdefault("external_links", {})
                            result["external_links"]["youtube"] = youtube_result.get("url")
            
            # CAS 5: Journaliste + célébrité (interview)
            elif any(c.get("profession") == "journalist" for c in celebrities_data):
                logger.info(f"🎙️ Détection d'interview")
                
                journalist = next((c for c in celebrities_data if c.get("profession") == "journalist"), None)
                subject = next((c for c in celebrities_data if c.get("profession") != "journalist"), None)
                
                if journalist and subject and self.youtube:
                    search_term = f"{subject.get('name')} {journalist.get('name')} interview"
                    if event_name:
                        search_term = f"{subject.get('name')} {event_name} interview"
                    
                    logger.info(f"ImageOrchestrator: Recherche YouTube interview: '{search_term}'")
                    youtube_results = await self.youtube.search_video(search_term, max_results=1)
                    if youtube_results and len(youtube_results) > 0:
                        result["youtube"] = youtube_results[0]
                        result.setdefault("external_links", {})
                        result["external_links"]["youtube"] = youtube_results[0].get("url")
            
            # ✅ CAS: Pochette d'album
            elif content_type == "album_cover" and self.spotify:
                search_term = album_name or song_name or title or artist
                if search_term:
                    logger.info(f"ImageOrchestrator: Recherche Spotify album: '{search_term}'")
                    spotify_result = await self.spotify.search_album(search_term)
                    if spotify_result:
                        result["spotify"] = spotify_result
                        result["image"] = spotify_result.get("image") or result.get("image")
                        result["artist"] = spotify_result.get("artist") or result.get("artist")
                        result["album"] = spotify_result.get("title")
                        result["year"] = spotify_result.get("release_date", "")[:4] if spotify_result.get("release_date") else None
                        logger.info(f"✅ Album Spotify trouvé: {spotify_result.get('title')}")
                        
                        if self.youtube:
                            youtube_result = await self.youtube.search_music_video(
                                spotify_result.get("title"),
                                spotify_result.get("artist")
                            )
                            if youtube_result:
                                result["youtube"] = youtube_result
            
            # ✅ CAS: Affiche de film
            elif content_type in ["movie_poster", "movie_scene"] and self.tmdb:
                search_term = movie_name or title or text_detected
                if search_term:
                    logger.info(f"ImageOrchestrator: Recherche TMDB film: '{search_term}'")
                    tmdb_result = await self.tmdb.search_movie(search_term, year)
                    if tmdb_result:
                        result["tmdb"] = tmdb_result
                        result["image"] = tmdb_result.get("image") or result.get("image")
                        result["title"] = tmdb_result.get("title")
                        result["movie_name"] = tmdb_result.get("title")
                        result["director"] = tmdb_result.get("director")
                        result["year"] = tmdb_result.get("release_date", "")[:4] if tmdb_result.get("release_date") else year
                        result["description"] = tmdb_result.get("description")
                        logger.info(f"✅ Film TMDB trouvé: {tmdb_result.get('title')}")
                        
                        if self.youtube:
                            youtube_result = await self.youtube.search_trailer(
                                tmdb_result.get("title", ""),
                                result.get("year")
                            )
                            if youtube_result:
                                result["youtube"] = youtube_result
            
            logger.info(f"ImageOrchestrator: Terminé - {result.get('title') or result.get('song_name') or result.get('movie_name') or 'inconnu'}")
            return result
            
        except Exception as e:
            logger.error(f"ImageOrchestrator: Erreur critique: {e}", exc_info=True)
            
            return {
                "type": "unknown",
                "title": None,
                "confidence": 0.0,
                "error": str(e),
                "detection": {"method": "failed", "error": str(e)}
            }
