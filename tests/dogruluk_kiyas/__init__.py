"""Tespit doğruluk takımı (docs/17 §14; GÖREV §4.8).

Etiketli saha karelerinde GERÇEK tespit motoruyla sınıf başına recall@IoU 0,5
ve AP50 ölçer. Pytest kapısı değildir ve veri depoya girmez: kareler KVKK
dayanağıyla toplanır, `veri/` altında (depo dışı) durur. Metrik fonksiyonları
tests/test_dogruluk_kiyas.py'de sahte kutularla sınanır.
"""
