import cv2

cap = cv2.VideoCapture(0)
print("OpenCV:", cv2.__version__)
while True:
    ok, frame = cap.read()
    if not ok:
        print("Webcam tidak terbaca")
        break
    cv2.imshow("Test webcam - tekan q untuk keluar", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cap.release()
cv2.destroyAllWindows()