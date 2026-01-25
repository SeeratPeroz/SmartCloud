from django.contrib.auth import get_user_model

User = get_user_model()

def normalize_username(s: str) -> str:
    # Remove spaces (Django disallows them in usernames)
    return "".join(ch for ch in s.strip() if ch != " ")

def create_unique_username(base: str) -> str:
    if not User.objects.filter(username=base).exists():
        return base
    i = 1
    while True:
        candidate = f"{base}-{i}"
        if not User.objects.filter(username=candidate).exists():
            return candidate
        i += 1

def run():
    rows = [
        ("AlNayar","SmileAlNaHealth"),
        ("AlHusam","SmileAlHuHealth"),
        ("AlYazan","SmileAlYaHealth"),
        ("AmSafwan","SmileAmSaHealth"),
        ("AoAouf","SmileAoAoHealth"),
        ("AsAli","SmileAsAlHealth"),
        ("AzSoheila","SmileAzSoHealth"),
        ("BeAnna","SmileBeAnHealth"),
        ("BeSilke","SmileBeSiHealth"),
        ("BlJohanna","SmileBlJoHealth"),
        ("BoFranziska","SmileBoFrHealth"),
        ("CaOmar Jose","SmileCaOmHealth"),
        ("CuMaja","SmileCuMaHealth"),
        ("DoMarica","SmileDoMaHealth"),
        ("EdChristina Maria","SmileEdChHealth"),
        ("ErHuriye","SmileErHuHealth"),
        ("GuClaudia","SmileGuClHealth"),
        ("HaMareike","SmileHaMaHealth"),
        ("HeJulia","SmileHeJuHealth"),
        ("HeFelicitas","SmileHeFeHealth"),
        ("HeMareike","SmileHeMaHealth"),
        ("JaMaher","SmileJaMaHealth"),
        ("JaJohanna","SmileJaJoHealth"),
        ("JaBasel","SmileJaBaHealth"),
        ("KiJungwook","SmileKiJuHealth"),
        ("LaAleksandar","SmileLaAlHealth"),
        ("LuSylvana","SmileLuSyHealth"),
        ("MaMonika","SmileMaMoHealth"),
        ("MaMajid","SmileMaMaHealth"),
        ("MeTamar","SmileMeTaHealth"),
        ("MoJoseph","SmileMoJoHealth"),
        ("NaBozhidara","SmileNaBoHealth"),
        ("NoFiras","SmileNoFiHealth"),
        ("ÖzGamze","SmileÖzGaHealth"),
        ("PoMarleen","SmilePoMaHealth"),
        ("PoDanielle","SmilePoDaHealth"),
        ("QuAndrea","SmileQuAnHealth"),
        ("SaInna","SmileSaInHealth"),
        ("ScKatharina","SmileScKaHealth"),
        ("ScMarlene Clara","SmileScMaHealth"),
        ("ScRüdiger","SmileScRüHealth"),
        ("ScGenevieve","SmileScGeHealth"),
        ("ScSusanne Ilka","SmileScSuHealth"),
        ("SpClaudia","SmileSpClHealth"),
        ("SpJonas","SmileSpJoHealth"),
        ("StKatja","SmileStKaHealth"),
        ("SuJana","SmileSuJaHealth"),
        ("TiMarianne","SmileTiMaHealth"),
        ("UtLena Johanna","SmileUtLeHealth"),
        ("VeEvgeniya","SmileVeEvHealth"),
        ("VoIvan","SmileVoIvHealth"),
        ("WePetra","SmileWePeHealth"),
        ("WeIsabel","SmileWeIsHealth"),
        ("WiMelanie","SmileWiMeHealth"),
        ("WoHelgard","SmileWoHeHealth"),
        ("ZäJonas","SmileZäJoHealth"),
    ]

    created, skipped = 0, 0
    for raw_username, password in rows:
        base = normalize_username(raw_username)
        username = create_unique_username(base)

        if User.objects.filter(username=username).exists():
            print(f"Skip (exists): {username}")
            skipped += 1
            continue

        User.objects.create_user(
            username=username,
            password=password,
            email=None,
            is_active=True
        )
        print(f"Created: {username}")
        created += 1

    print(f"Done. created={created}, skipped={skipped}")

# So it works with: python manage.py shell < import_users.py
if __name__ == "__main__":
    run()
