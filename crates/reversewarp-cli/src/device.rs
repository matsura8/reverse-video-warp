use std::fmt;
use std::str::FromStr;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CudaDevice {
    index: u32,
}

impl CudaDevice {
    pub const fn index(&self) -> u32 {
        self.index
    }
}

impl fmt::Display for CudaDevice {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "cuda:{}", self.index)
    }
}

impl FromStr for CudaDevice {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let index = value
            .strip_prefix("cuda:")
            .ok_or_else(|| "device must use cuda:N; CPU processing is debug-only".to_owned())?;
        if index.is_empty() || (index.len() > 1 && index.starts_with('0')) {
            return Err("CUDA device index must be a canonical non-negative integer".to_owned());
        }
        let index = index
            .parse::<u32>()
            .map_err(|_| "CUDA device index must be a non-negative integer".to_owned())?;
        Ok(Self { index })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_cuda_index() {
        let device = "cuda:12".parse::<CudaDevice>().unwrap();
        assert_eq!(device.index(), 12);
        assert_eq!(device.to_string(), "cuda:12");
    }

    #[test]
    fn rejects_cpu_and_ambiguous_indexes() {
        assert!("cpu".parse::<CudaDevice>().is_err());
        assert!("cuda:01".parse::<CudaDevice>().is_err());
        assert!("cuda:-1".parse::<CudaDevice>().is_err());
    }
}
