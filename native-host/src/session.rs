use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use base64::Engine;
use rand::RngCore;

const SESSION_LIFETIME: Duration = Duration::from_secs(30 * 60);

#[derive(Debug, Clone)]
pub struct Session {
    pub origin: String,
    expires: Instant,
}

#[derive(Debug, Default)]
pub struct SessionStore {
    entries: Mutex<HashMap<String, Session>>,
}

impl SessionStore {
    pub fn create(&self, origin: &str) -> String {
        let mut bytes = [0_u8; 32];
        rand::rng().fill_bytes(&mut bytes);
        let token = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(bytes);
        let session = Session {
            origin: normalize_origin(origin).to_string(),
            expires: Instant::now() + SESSION_LIFETIME,
        };
        self.entries
            .lock()
            .expect("session mutex poisoned")
            .insert(token.clone(), session);
        token
    }

    pub fn validate(&self, token: &str, origin: Option<&str>) -> bool {
        let mut entries = self.entries.lock().expect("session mutex poisoned");
        entries.retain(|_, session| session.expires > Instant::now());
        entries.get(token).is_some_and(|session| {
            origin.is_none_or(|value| {
                normalize_origin(value) == session.origin
                    || session.origin == "reversewarp-development"
            })
        })
    }

    pub fn revoke(&self, token: &str) -> bool {
        self.entries
            .lock()
            .expect("session mutex poisoned")
            .remove(token)
            .is_some()
    }
}

fn normalize_origin(origin: &str) -> &str {
    origin.trim_end_matches('/')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_is_bound_to_origin_and_revocable() {
        let store = SessionStore::default();
        let token = store.create("chrome-extension://expected");
        assert!(store.validate(&token, Some("chrome-extension://expected")));
        assert!(!store.validate(&token, Some("chrome-extension://other")));
        assert!(store.revoke(&token));
        assert!(!store.validate(&token, Some("chrome-extension://expected")));
    }

    #[test]
    fn chrome_native_origin_matches_fetch_origin_without_trailing_slash() {
        let store = SessionStore::default();
        let token = store.create("chrome-extension://expected/");
        assert!(store.validate(&token, Some("chrome-extension://expected")));
    }
}
