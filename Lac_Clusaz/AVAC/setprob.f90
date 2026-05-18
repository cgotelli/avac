! setprob.f90 for AVAC 4: version = 2.0

subroutine setprob

    implicit none

    character*12 fname, free_surface
    integer iunit
    double precision :: rho, mu, xi, C, u_cr
    double precision :: d_0, x_b, grav, theta
    integer :: imodel, itype_init
    common /rheology/ rho, mu, xi, C, u_cr, imodel
    character(len=20) :: constitutive_model
    common /initial_conditions/ free_surface
    common /initial_depth/ d_0, theta, x_b

    !
    !     # read data values for this problem
    !
    iunit = 7
    fname = 'setprob.data'
    !     # open the unit with new routine from Clawpack 4.4 to skip over
    !     # comment lines starting with #:
    call opendatafile(iunit, fname)

    !     # Rheological parameters used in src2.f90
    read(7,*) rho
    read(7,*) mu
    read(7,*) xi
    read(7,*) C
    read(7,*) u_cr
    read(7,*) constitutive_model
    read(7,*) itype_init
!     # These parameters are used in qinit.f90 (synthetic topography only)
    if (itype_init == 0) then
        read(7,*) theta
        read(7,*) free_surface
        read(7,*) d_0
        read(7,*) x_b
    end if
    close(unit=7)

    !     # Convert constitutive model name to integer flag
    !     # imodel = 1  =>  Coulomb
    !     # imodel = 2  =>  Voellmy
    !     # imodel = 3  =>  cohesive_Voellmy
    if (trim(constitutive_model) == 'Coulomb') then
        imodel = 1
    else if (trim(constitutive_model) == 'Voellmy') then
        imodel = 2
    else if (trim(constitutive_model) == 'cohesive_Voellmy') then
        imodel = 3
    else
        print *, 'ERROR in setprob: unknown constitutive_model = ', &
                 trim(constitutive_model)
        print *, 'Valid options are: Coulomb, Voellmy, cohesive_Voellmy'
        stop
    end if

    print *, 'rho (snow density) = ', rho
    print *, 'mu                 = ', mu
    print *, 'xi                 = ', xi
    print *, 'C (cohesion, Pa)   = ', C
    print *, 'u_cr (m/s)         = ', u_cr
    print *, 'constitutive_model = ', trim(constitutive_model), &
             '  (imodel=', imodel, ')'

end subroutine setprob
