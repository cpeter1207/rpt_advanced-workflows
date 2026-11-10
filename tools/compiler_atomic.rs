//! Compile-only reduction of the SIP stack's optimized atomic trait-object slot.
//! Older LLVM backends fail instruction selection for this valid Rust pattern.

use std::sync::{
    Arc,
    atomic::{AtomicPtr, Ordering},
};

/// Opaque connector shared by signaling tasks.
pub trait Connector: Send + Sync {}

static CONNECTOR: AtomicPtr<Arc<dyn Connector>> = AtomicPtr::new(std::ptr::null_mut());

/// Publish a permanently retained connector, matching the upstream compile case.
pub fn publish(connector: Arc<dyn Connector>) {
    CONNECTOR.store(Box::leak(Box::new(connector)), Ordering::Release);
}

/// Remove the published pointer without reclaiming its retained allocation.
pub fn clear() {
    CONNECTOR.store(std::ptr::null_mut(), Ordering::Release);
}

/// Clone the retained connector through the acquired atomic pointer.
pub fn current() -> Option<Arc<dyn Connector>> {
    let pointer = CONNECTOR.load(Ordering::Acquire);
    if pointer.is_null() {
        None
    } else {
        // Published allocations are permanently retained in this compile fixture.
        unsafe { Some((*pointer).clone()) }
    }
}
