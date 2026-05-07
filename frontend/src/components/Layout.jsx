import React from 'react';
import Header from './Header';
import Footer from './Footer';

const Layout = ({ children }) => {
  return (
    <div className="flex flex-col min-h-screen">
      <Header />
      <main className="flex-grow">
        {children} {/* This is where your page content (Dashboard, etc.) will go */}
      </main>
      <Footer />
    </div>
  );
};

export default Layout;