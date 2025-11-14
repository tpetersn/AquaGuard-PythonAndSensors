# ov_yolo11_webcam.py
import os, time
import numpy as np
import cv2

# ---- COCO labels ----
COCO = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light",
    "fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow",
    "elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase",
    "frisbee","skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket",
    "bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple","sandwich",
    "orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch","potted plant",
    "bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone","microwave",
    "oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"
]

MODEL_PT = "yolo11n.pt"
IR_DIR = "yolo11n_openvino_416"
IMG_SIZE = 416        
CONF_TH = 0.30
IOU_TH  = 0.45
CLASS_FILTER = None    #{0} for person-only, or None for all

# ---- utils ----
def letterbox(img, new_shape=(416,416), color=(114,114,114)):
    h, w = img.shape[:2]
    r = min(new_shape[0]/h, new_shape[1]/w)
    nh, nw = int(round(h*r)), int(round(w*r))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    top = (new_shape[0]-nh)//2; bottom = new_shape[0]-nh-top
    left = (new_shape[1]-nw)//2; right = new_shape[1]-nw-left
    out = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return out, r, (left, top)

def iou_np(a, bs):
    x11,y11,x12,y12 = a
    x21,y21,x22,y22 = bs[:,0],bs[:,1],bs[:,2],bs[:,3]
    xi1 = np.maximum(x11,x21); yi1 = np.maximum(y11,y21)
    xi2 = np.minimum(x12,x22); yi2 = np.minimum(y12,y21+ (y22-y21)) 
    yi2 = np.minimum(y12,y22)
    inter = np.maximum(0, xi2 - xi1) * np.maximum(0, yi2 - yi1)
    area_a = (x12-x11)*(y12-y11); area_b = (x22-x21)*(y22-y21)
    return inter/(area_a + area_b - inter + 1e-6)

def nms_np(boxes, scores, th=0.45):
    if len(boxes)==0: return []
    idxs = scores.argsort()[::-1]
    keep=[]
    while len(idxs):
        i = idxs[0]; keep.append(i)
        if len(idxs)==1: break
        ious = iou_np(boxes[i], boxes[idxs[1:]])
        idxs = idxs[1:][ious < th]
    return keep

def export_openvino_ir():
    if os.path.isdir(IR_DIR):
        return IR_DIR
    from ultralytics import YOLO
    m = YOLO(MODEL_PT)
    # export to OpenVINO IR (FP16) at 416 for speed
    m.export(format="openvino", imgsz=IMG_SIZE, half=True, dynamic=False, simplify=True)
    base = "yolo11n_openvino_model"
    if os.path.isdir(base):
        os.replace(base, IR_DIR)
    else:
        latest = None
        for d in [p for p in os.listdir(".") if os.path.isdir(p)]:
            if d.endswith("_openvino_model"):
                latest = d
        if latest:
            os.replace(latest, IR_DIR)
    return IR_DIR

def main():
    ir = export_openvino_ir()

    import openvino as ov
    core = ov.Core()
    model = core.read_model(model=os.path.join(ir, "yolo11n.xml"))  
    compiled = core.compile_model(model, "CPU", {"PERFORMANCE_HINT":"LATENCY"})
    input_tensor = compiled.inputs[0]
    output_tensor = compiled.outputs[0]

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

    ok, frame = cap.read()
    if not ok:
        print("Failed to open webcam.")
        return

    H,W,_ = frame.shape
    t0=time.time(); n=0

    while True:
        ok, frame = cap.read()
        if not ok: break

        lb, scale, pad = letterbox(frame, (IMG_SIZE, IMG_SIZE))
        blob = lb[:, :, ::-1].transpose(2,0,1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, 0)

        res = compiled.infer_new_request({input_tensor: blob})[output_tensor]
        pred = res[0]
        if pred.shape[0] in (84,85):
            pred = pred.T
        C = pred.shape[1]
        xywh = pred[:, :4]
        if C == 85:
            obj = pred[:,4:5]
            cls = pred[:,5:]
            scores = (obj*cls).max(1)
            ids    = (obj*cls).argmax(1)
        else:
            cls = pred[:,4:]
            scores = cls.max(1)
            ids    = cls.argmax(1)

        mask = scores >= CONF_TH
        if CLASS_FILTER is not None:
            mask &= np.isin(ids, list(CLASS_FILTER))
        xywh, scores, ids = xywh[mask], scores[mask], ids[mask]

        if len(xywh):
            cx,cy,w,h = xywh.T
            boxes = np.stack([cx-w/2, cy-h/2, cx+w/2, cy+h/2], 1)
            # NMS per-class
            final=[]
            for c in np.unique(ids):
                m = ids==c
                keep = nms_np(boxes[m], scores[m], th=IOU_TH)
                for k in keep:
                    final.append((boxes[m][k], float(scores[m][k]), int(c)))

            # reverse letterbox
            (left, top) = pad
            drawn = frame.copy()
            for box, sc, cid in final:
                x1,y1,x2,y2 = box
                x1-=left; x2-=left; y1-=top; y2-=top
                x1/=scale; x2/=scale; y1/=scale; y2/=scale
                x1=int(np.clip(x1,0,W-1)); y1=int(np.clip(y1,0,H-1))
                x2=int(np.clip(x2,0,W-1)); y2=int(np.clip(y2,0,H-1))
                name = COCO[cid] if 0 <= cid < len(COCO) else str(cid)
                cv2.rectangle(drawn,(x1,y1),(x2,y2),(0,255,0),2)
                label = f"{name} {sc:.2f}"
                ((tw,th),_) = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                y0 = max(20, y1-6)
                cv2.rectangle(drawn,(x1,y0-th-6),(x1+tw+6,y0),(0,255,0),-1)
                cv2.putText(drawn,label,(x1+3,y0-3),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,0),2)

        else:
            drawn = frame

        n+=1; fps = n / max(1e-6, (time.time()-t0))
        cv2.putText(drawn, f"OpenVINO CPU | {fps:.1f} FPS", (10,30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        cv2.imshow("YOLO11n OpenVINO", drawn)
        if cv2.waitKey(1) & 0xFF in (27, ord('q')): break

    cap.release(); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
