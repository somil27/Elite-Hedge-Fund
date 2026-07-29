import { useQuery } from '@tanstack/react-query'
import { getCycle, getPendingReview } from '../store/api'

export function useCycle(cycleId: string | undefined, pollInterval = 3000) {
  const { 
    data: cycle, 
    isLoading: loading, 
    error,
    refetch: refresh
  } = useQuery({
    queryKey: ['cycle', cycleId],
    queryFn: async () => {
      if (!cycleId) return null
      return getCycle(cycleId)
    },
    enabled: !!cycleId,
    refetchInterval: (query) => {
      const currentStatus = query.state?.data?.status;
      if (['executed', 'rejected', 'failed'].includes(currentStatus)) {
        return false; // Stop polling
      }
      return pollInterval;
    }
  })

  // Only fetch review if the cycle is awaiting human
  const { data: review } = useQuery({
    queryKey: ['review', cycleId],
    queryFn: () => getPendingReview(cycleId!),
    enabled: !!cycleId && cycle?.awaiting_human === true,
  })

  return { 
    cycle, 
    review, 
    loading, 
    error: error?.message ?? null, 
    refresh 
  }
}
