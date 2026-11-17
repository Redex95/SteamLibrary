# Steam Library Explorer

Steam Library Explorer è un sito per consultare i giochi posseduti e quelli condivisi tramite Steam Families e confrontare, in modo indicativo, i requisiti pubblicati su Steam con le specifiche del proprio PC. Il progetto è stato realizzato con assistenza AI; **l’applicazione non chiama modelli o servizi AI** per analizzare i giochi.

Il risultato è un’euristica, non un benchmark: non misura FPS e non garantisce che un gioco funzioni bene. I requisiti Steam sono testi scritti dagli sviluppatori, e il programma riconosce solo alcuni modelli di CPU e GPU.

## Come funziona

1. Inserisci la Steam Web API key e il tuo SteamID64. Il token `webapi_token` è facoltativo e serve per includere i giochi condivisi tramite Steam Families.
2. Il browser invia i dati alle route Flask dello stesso sito. Flask li usa per interrogare Steam e restituisce i risultati al browser.
3. Il browser salva la libreria e i requisiti e calcola filtri, punteggi e compatibilità.

Le route Flask `/api/owned`, `/api/family`, `/api/players` e `/api/details` fanno da proxy verso Steam. `/api/pc` riceve i nomi di CPU e GPU e restituisce i punteggi stimati dalle tabelle contenute nel server.

## Endpoint esterni usati

### Steam Web API — `api.steampowered.com`

- `IPlayerService/GetOwnedGames/v1/` — legge i giochi personali, i nomi, gli AppID e il tempo di gioco. La richiesta include `include_appinfo=1` e `include_played_free_games=1`. La visibilità dei giochi deve consentire la lettura dei dati. [Riferimento Steamworks](https://partner.steamgames.com/doc/webapi/iplayerservice?language=english)
- `IFamilyGroupsService/GetFamilyGroupForUser/v1/` — ricava il gruppo famiglia associato allo SteamID usando il token fornito.
- `IFamilyGroupsService/GetSharedLibraryApps/v1/` — legge i giochi condivisi e gli SteamID dei proprietari. Queste chiamate vengono fatte solo se inserisci il token famiglia.
- `ISteamUser/GetPlayerSummaries/v2/` — recupera i nomi pubblici dei proprietari dei giochi, fino a 100 SteamID per richiesta. [Riferimento Steamworks](https://partner.steamgames.com/doc/webapi/isteamuser)

### Steam Store — `store.steampowered.com`

- `/api/appdetails` — per ogni gioco recupera il tipo e i requisiti PC minimi e consigliati, con lingua inglese e paese Italia. La chiamata non usa la tua API key.
- `/app/{appid}` — pagina Steam aperta quando selezioni il titolo di un gioco.
- `/pointssummary/ajaxgetasyncconfig` — pagina collegata per recuperare manualmente il token famiglia. Il sito non effettua automaticamente l’accesso al tuo account Steam.
- `/dev/apikey` — pagina Steam per creare o consultare una Web API key.

### Altri collegamenti

- `steamid.io` — link esterno per trovare il proprio SteamID64; l’app non invia lì i dati inseriti nel modulo.
- `cdn.cloudflare.steamstatic.com/steam/apps/{appid}/capsule_184x69.jpg` — immagini di copertina mostrate nell’elenco dei giochi.

Gli endpoint Web API principali sono documentati nella [documentazione Steam Web API](https://steamcommunity.com/dev/). Le chiamate partono dal server Flask, così il browser non deve contattare direttamente le API Steam.

## Come vengono usati i dati inseriti

| Dato | Uso |
|---|---|
| **API key Steam** | Inviata alla route `/api/owned` per leggere la libreria personale e a `/api/players` per risolvere i nomi dei proprietari. Flask la inoltra a Steam nelle richieste corrispondenti. |
| **SteamID64** | Inviato insieme all’API key per leggere i giochi personali; usato anche con il token famiglia, se presente. |
| **Token `webapi_token`** | Inviato a `/api/family`, che lo usa per interrogare il gruppo famiglia e i giochi condivisi. È facoltativo. |
| **CPU e GPU** | Salvate nel browser e inviate a `/api/pc` per riconoscere i modelli e calcolare i relativi punteggi. |
| **RAM** | Salvata e usata nel browser nel calcolo del punteggio e nel confronto con la RAM richiesta. Non viene inviata alle API Steam. |
| **Filtri e ordinamento** | Applicati nel browser ai dati già caricati; non sono inviati a Steam. |

Le credenziali e le specifiche vengono salvate nel `localStorage` del browser, nell’elemento `steamlib.settings.v1`. I punteggi del PC sono salvati in `steamlib.pc.v1`. Libreria e requisiti dei giochi sono conservati in IndexedDB, nel database `steamlib`, archivio `kv`, con le chiavi `library` e `details`.

Questi dati restano nel profilo del browser e nell’origine del sito usata per aprirlo: non vengono sincronizzati fra dispositivi. L’applicazione non li scrive su file o database del server. Le richieste contenenti le credenziali passano comunque dal server Flask e vengono inoltrate a Steam; il codice dell’app non le persiste lato server. **Cancella dati salvati** rimuove le impostazioni locali, la libreria e i requisiti memorizzati.

## Come viene stimata la compatibilità

Il programma estrae dai requisiti testuali i modelli hardware riconosciuti e i valori di RAM e spazio. Quando sono disponibili, dà priorità ai requisiti consigliati e usa quelli minimi come ripiego. I modelli non riconosciuti o i requisiti non presenti possono produrre un risultato “non determinabile”.

Per ordinare i giochi usa questa stima:

```text
punteggio = GPU + 0,5 × CPU + 1,5 × RAM in GB
```

La compatibilità valuta separatamente GPU, CPU e RAM e mostra il componente con il risultato peggiore. Le soglie sono euristiche: GPU `1,0 / 1,25`, CPU `1,3 / 1,8` come rapporto tra requisito e PC; la RAM è segnalata come insufficiente quando il requisito supera quella disponibile. Non sono considerate risoluzione, preset grafici, driver, ottimizzazione, upscaling o prestazioni misurate dagli utenti.

Per rispettare i limiti di Steam, i requisiti vengono caricati in piccoli gruppi e il browser rallenta le richieste quando raggiunge la soglia configurata. Se Steam risponde con un limite temporaneo, l’app attende e può permettere di riprovare i requisiti mancanti.

## Avvio locale

Richiede Python 3.14 o superiore. Dalla cartella del progetto:

```powershell
uv sync
uv run python app.py
```

Apri <http://127.0.0.1:5057>.

## Nota sulla privacy

Il sito non richiede la password Steam. Le credenziali inserite sono quelle della Web API key e, facoltativamente, il token famiglia. Usa il progetto solo su un indirizzo di cui ti fidi: il browser invia questi valori al server del sito perché possa chiamare Steam per tuo conto.
