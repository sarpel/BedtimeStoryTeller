# Bu modül, ses verilerini çalmak için bir desen sağlar.
# Gerçek bir uygulama için `simpleaudio` gibi platformlar arası çalışan
# ve kurulumu kolay bir kütüphane önerilir.
# Örnek: pip install simpleaudio

# import simpleaudio as sa # Gerçek uygulamada bu satır aktif edilebilir.

class AudioPlayer:
    """
    Ham ses baytlarını alan ve bunları oynatan basit bir sınıf.
    Bu, TTS (Text-to-Speech) servisinden gelen streaming verileriyle
    uyumlu bir yapı kurmayı kolaylaştırır.
    """
    def __init__(self):
        """AudioPlayer başlatıldığında hazır olduğunu belirtir."""
        print("AudioPlayer Initialized: Ready to play audio.")

    def play(self, audio_data: bytes):
        """
        Verilen ses baytlarını oynatır. Bu metodun engellememesi (non-blocking)
        veya ayrı bir thread'de çalışması, akıcı bir kullanıcı deneyimi için önemlidir.

        Args:
            audio_data (bytes): Oynatılacak ham ses verisi.
        """
        if not audio_data:
            print("Warning: No audio data received to play.")
            return

        print(f"Playing audio chunk of {len(audio_data)} bytes...")

        # --- GERÇEK UYGULAMA DESENİ ---
        # Burada `simpleaudio` gibi bir kütüphane kullanılır.
        # Bu yapı, kütüphane detaylarını projenin geri kalanından soyutlar.
        try:
            # Örnek olarak, 24kHz, 16-bit mono bir ses varsayalım.
            # Bu ayarlar kullandığınız TTS servisine göre değişir.
            # play_obj = sa.play_buffer(audio_data, 1, 2, 24000)
            # play_obj.wait_done()  # Senkron oynatma için bekle. Asenkron için bu satır kaldırılır.
            pass # Örnek olduğu için geçiyoruz.
        except Exception as e:
            # Gerçek uygulamada hata yönetimi kritik öneme sahiptir.
            print(f"Error playing audio: {e}")
        # --------------------------------

        print("Finished playing audio chunk.")