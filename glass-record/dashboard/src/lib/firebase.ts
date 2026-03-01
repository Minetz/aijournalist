import { initializeApp, getApps } from "firebase/app";
import { getFirestore, collection, doc, onSnapshot,
         query, orderBy, limit, getDocs } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
export const db = getFirestore(app);

// ── Subscription helpers ────────────────────────────────────────────────────

export function subscribeToJournalist(
  journalistId: string,
  callback: (data: Record<string, unknown>) => void,
) {
  const ref = doc(db, "journalists", journalistId);
  return onSnapshot(ref, (snap) => {
    if (snap.exists()) callback({ id: snap.id, ...snap.data() });
  });
}

export function subscribeToActivityLog(
  journalistId: string,
  callback: (entries: Record<string, unknown>[]) => void,
) {
  const q = query(
    collection(db, "journalists", journalistId, "activity_log"),
    orderBy("timestamp", "desc"),
    limit(50),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToEvidenceLocker(
  journalistId: string,
  callback: (items: Record<string, unknown>[]) => void,
) {
  const q = query(
    collection(db, "journalists", journalistId, "evidence_locker"),
    orderBy("credibility_score", "desc"),
    limit(30),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToComplianceLog(
  journalistId: string,
  callback: (entries: Record<string, unknown>[]) => void,
) {
  const q = query(
    collection(db, "journalists", journalistId, "compliance_log"),
    orderBy("timestamp", "desc"),
    limit(20),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export function subscribeToStories(
  journalistId: string,
  callback: (stories: Record<string, unknown>[]) => void,
) {
  const q = query(
    collection(db, "journalists", journalistId, "stories"),
    orderBy("published_at", "desc"),
    limit(10),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => ({ id: d.id, ...d.data() })));
  });
}

export async function getAllJournalists(): Promise<Record<string, unknown>[]> {
  const snap = await getDocs(collection(db, "journalists"));
  return snap.docs.map((d) => ({ id: d.id, ...d.data() }));
}
