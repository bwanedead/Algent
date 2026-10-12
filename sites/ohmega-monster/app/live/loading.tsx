import GlobeSpinner from "@/components/GlobeSpinner";

// Shown by Next while /live fetches its snapshots on the server (route-level loading UI).
export default function LiveLoading() {
  return (
    <div className="intel-page live-page">
      <div className="globe-page">
        <GlobeSpinner size={112} caption="Loading live data" />
      </div>
    </div>
  );
}
