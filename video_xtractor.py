from colorama import init, Fore, Style
from video_xtractor_def import get_video_url_from_user, download_video

# INITIALISATION DE COLORAMA
init(autoreset=True)


def main() -> None:
    urls = get_video_url_from_user()

    for url in urls:
        try:
            download_video(url)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Interrompu par l'utilisateur.{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}Erreur lors du téléchargement / traitement : {e}{Style.RESET_ALL}")

    # Important: quand l'app est lancée en double-clic (PyInstaller), la fenêtre se ferme sinon.
    input(f"\n{Style.BRIGHT}{Fore.MAGENTA}Appuyez sur Entrée pour quitter...{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
