export default function Home() {
  return (
    <div className="flex min-h-screen items-center bg-[#10100f] px-6 text-[#f5f3ed] sm:px-10">
      <main className="mx-auto w-full max-w-3xl py-24">
        <p className="text-sm font-medium tracking-[0.24em] text-[#a9d5a4]">
          QUANTRADE
        </p>
        <h1 className="mt-6 max-w-xl text-4xl font-semibold tracking-tight sm:text-6xl">
          Research, made legible.
        </h1>
        <p className="mt-6 max-w-lg text-lg leading-8 text-[#bab8b0]">
          The private-beta research foundation is being prepared with dated,
          source-attributed market and filing data.
        </p>
        <div className="mt-12 border-t border-[#3a3a36] pt-5 text-sm text-[#98968e]">
          Data capability validation in progress.
        </div>
      </main>
    </div>
  );
}
