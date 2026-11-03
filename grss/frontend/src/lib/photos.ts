// NASA photography (public domain), see public/img/CREDITS.txt.
export const PHOTOS = {
  sunrise: "/img/hero-sunrise.jpg",
  dsn: "/img/hero-dsn.jpg",
  cubesat: "/img/hero-cubesat.jpg",
  aurora: "/img/aurora.jpg",
  aurora2: "/img/aurora-2.jpg",
  cubesatDeploy: "/img/cubesat-deploy.jpg",
  dsnNew: "/img/dsn-new.jpg",
  dsnTracks: "/img/dsn-tracks.jpg",
  sentinel6: "/img/sentinel6.jpg",
  earthObs: "/img/earth-obs.jpg",
  earthNight: "/img/earth-night.jpg",
  missionControl: "/img/mission-control.jpg",
  aqua: "/img/aqua.jpg",
};

export const PHOTO_LIST = Object.values(PHOTOS);

export const fmtDay = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export const fmtLong = (iso: string) =>
  new Date(iso).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
